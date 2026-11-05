"""AWS layout for the concierge.

The API is a Fargate service. Sessions are a DynamoDB table. Catalog vectors
are an OpenSearch Serverless collection. The shopper UI is a private S3 bucket
behind CloudFront. Tasks run in public subnets so the stack does not include a
NAT gateway.

Deploying this stack is a separate step. The tests in this repository do not
create these resources.
"""

import aws_cdk as cdk
from aws_cdk import CfnOutput, CfnParameter, Duration, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_opensearchserverless as aoss
from aws_cdk import aws_s3 as s3
from constructs import Construct

COLLECTION = "kitline"


class KitlineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        image_uri = CfnParameter(
            self,
            "ImageUri",
            type="String",
            description="Kitline API image, including the tag. Build it from backend/Dockerfile.",
        )

        table = dynamodb.Table(
            self,
            "Sessions",
            table_name="kitline-sessions",
            partition_key=dynamodb.Attribute(name="session_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
        )

        encryption = aoss.CfnSecurityPolicy(
            self,
            "VectorEncryption",
            name="kitline-encrypt",
            type="encryption",
            policy=(
                '{"Rules":[{"ResourceType":"collection","Resource":["collection/kitline"]}],'
                '"AWSOwnedKey":true}'
            ),
        )
        network = aoss.CfnSecurityPolicy(
            self,
            "VectorNetwork",
            name="kitline-network",
            type="network",
            policy=(
                '[{"Rules":[{"ResourceType":"collection","Resource":["collection/kitline"]},'
                '{"ResourceType":"dashboard","Resource":["collection/kitline"]}],'
                '"AllowFromPublic":true}]'
            ),
        )
        collection = aoss.CfnCollection(
            self,
            "Vectors",
            name=COLLECTION,
            type="VECTORSEARCH",
            description="Product vectors for Kitline catalog search.",
        )
        collection.add_resource_dependency(encryption)
        collection.add_resource_dependency(network)

        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24)
            ],
        )

        task_role = iam.Role(
            self,
            "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Kitline API: Bedrock, the session table, and the vector collection.",
        )
        table.grant_read_write_data(task_role)
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.*",
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0",
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/*",
                ],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["aoss:APIAccessAll"],
                resources=[collection.attr_arn],
            )
        )

        data_access = aoss.CfnAccessPolicy(
            self,
            "VectorDataAccess",
            name="kitline-data",
            type="data",
            policy=cdk.Fn.sub(
                '[{"Description":"Kitline task role","Principal":["${Role}"],'
                '"Rules":[{"ResourceType":"collection","Resource":["collection/kitline"],'
                '"Permission":["aoss:CreateCollectionItems","aoss:UpdateCollectionItems",'
                '"aoss:DescribeCollectionItems"]},'
                '{"ResourceType":"index","Resource":["index/kitline/*"],'
                '"Permission":["aoss:CreateIndex","aoss:UpdateIndex","aoss:DescribeIndex",'
                '"aoss:ReadDocument","aoss:WriteDocument"]}]}]',
                {"Role": task_role.role_arn},
            ),
        )
        data_access.add_resource_dependency(collection)

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "Api",
            vpc=vpc,
            assign_public_ip=True,
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            public_load_balancer=True,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry(image_uri.value_as_string),
                container_port=8000,
                task_role=task_role,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="kitline",
                    log_retention=logs.RetentionDays.ONE_WEEK,
                ),
                environment={
                    "KITLINE_MODE": "bedrock",
                    "KITLINE_EMBEDDINGS": "bedrock",
                    "KITLINE_VECTOR_STORE": "opensearch",
                    "KITLINE_OPENSEARCH_ENDPOINT": cdk.Fn.join("", ["https://", collection.attr_collection_endpoint]),
                    "KITLINE_OPENSEARCH_INDEX": "kitline-products",
                    "KITLINE_SESSION_STORE": "dynamodb",
                    "KITLINE_SESSION_TABLE": table.table_name,
                    "KITLINE_AWS_REGION": self.region,
                    "KITLINE_BEDROCK_REGION": self.region,
                    "KITLINE_BEDROCK_MODEL_ID": "global.anthropic.claude-sonnet-4-6",
                },
            ),
        )
        service.target_group.configure_health_check(
            path="/api/health",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
        )
        service.service.node.add_dependency(data_access)

        web_bucket = s3.Bucket(
            self,
            "Web",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
        )
        distribution = cloudfront.Distribution(
            self,
            "WebCdn",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(web_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
        )

        CfnOutput(self, "ApiUrl", value=f"http://{service.load_balancer.load_balancer_dns_name}")
        CfnOutput(self, "WebUrl", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "SessionTable", value=table.table_name)
        CfnOutput(self, "VectorEndpoint", value=collection.attr_collection_endpoint)
        CfnOutput(self, "WebBucket", value=web_bucket.bucket_name)
