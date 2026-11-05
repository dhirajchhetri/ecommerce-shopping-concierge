#!/usr/bin/env python3
"""Synthesize the Kitline stack. `python3 app.py` writes cdk.out."""

import os

import aws_cdk as cdk

from kitline_stack import KitlineStack

account = os.getenv("CDK_DEFAULT_ACCOUNT")
region = os.getenv("CDK_DEFAULT_REGION", "us-west-2")

app = cdk.App(outdir=os.getenv("CDK_OUTDIR", "cdk.out"))
KitlineStack(
    app,
    "KitlineStack",
    env=cdk.Environment(account=account, region=region),
    description="Kitline shopping concierge: API, sessions, and a vector collection.",
)
app.synth()
