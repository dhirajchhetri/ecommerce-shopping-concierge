from datetime import date

import boto3
import pytest
from moto import mock_aws

from kitline.schemas import SessionOut
from kitline.sessions import DynamoSessionStore, FileSessionStore, MemorySessionStore


def _record() -> SessionOut:
    return SessionOut(
        session_id="ses_abc123def456",
        created_at="2026-11-05T00:00:00+00:00",
        updated_at="2026-11-05T00:00:00+00:00",
        turns=[],
    )


def test_memory_store_round_trip():
    store = MemorySessionStore()
    record = _record()
    store.put(record)
    record.updated_at = "2026-11-05T01:00:00+00:00"
    loaded = store.get(record.session_id)
    assert loaded is not None
    assert loaded.updated_at == "2026-11-05T00:00:00+00:00"
    assert store.get("ses_missing0000") is None


def test_file_store_rejects_path_tricks(tmp_path):
    store = FileSessionStore(str(tmp_path))
    record = _record()
    store.put(record)
    assert store.get(record.session_id) == record
    with pytest.raises(ValueError):
        store.put(record.model_copy(update={"session_id": "../secret"}))
    assert store.get("../secret") is None


@mock_aws
def test_dynamodb_store_round_trip():
    client = boto3.client("dynamodb", region_name="us-west-2")
    client.create_table(
        TableName="kitline-sessions",
        KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    store = DynamoSessionStore("kitline-sessions", region="us-west-2", client=client)
    record = _record()
    record.updated_at = "2026-11-05T02:00:00+00:00"
    store.put(record)
    loaded = store.get(record.session_id)
    assert loaded == record
    assert store.get("ses_missing0000") is None
    item = client.get_item(TableName="kitline-sessions", Key={"session_id": {"S": record.session_id}})
    assert item["Item"]["updated_at"]["S"] == record.updated_at
    assert date.fromisoformat("2026-11-05")
