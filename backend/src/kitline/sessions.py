"""Session memory.

The in-memory store is the test and offline default. The file store is for
docker-compose. DynamoDB is the AWS store: one item per session, document JSON
in a string attribute so the shape can change without a migration.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

from kitline.schemas import SessionOut

_SESSION_ID = re.compile(r"ses_[a-f0-9]{12}")


class SessionStore(Protocol):
    def get(self, session_id: str) -> SessionOut | None: ...

    def put(self, record: SessionOut) -> None: ...


class MemorySessionStore:
    def __init__(self) -> None:
        self._items: dict[str, SessionOut] = {}

    def get(self, session_id: str) -> SessionOut | None:
        record = self._items.get(session_id)
        return record.model_copy(deep=True) if record else None

    def put(self, record: SessionOut) -> None:
        self._items[record.session_id] = record.model_copy(deep=True)


class FileSessionStore:
    def __init__(self, directory: str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path | None:
        if not _SESSION_ID.fullmatch(session_id):
            return None
        return self.directory / f"{session_id}.json"

    def get(self, session_id: str) -> SessionOut | None:
        path = self._path(session_id)
        if path is None or not path.is_file():
            return None
        return SessionOut.model_validate_json(path.read_text(encoding="utf-8"))

    def put(self, record: SessionOut) -> None:
        path = self._path(record.session_id)
        if path is None:
            raise ValueError("session_id must look like ses_ plus 12 hex characters.")
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")


class DynamoSessionStore:
    def __init__(self, table_name: str, region: str, client=None) -> None:
        self.table_name = table_name
        if client is None:
            import boto3

            client = boto3.client("dynamodb", region_name=region)
        self.client = client

    def get(self, session_id: str) -> SessionOut | None:
        response = self.client.get_item(
            TableName=self.table_name,
            Key={"session_id": {"S": session_id}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not item or "document" not in item:
            return None
        return SessionOut.model_validate_json(item["document"]["S"])

    def put(self, record: SessionOut) -> None:
        self.client.put_item(
            TableName=self.table_name,
            Item={
                "session_id": {"S": record.session_id},
                "updated_at": {"S": record.updated_at},
                "document": {"S": json.dumps(record.model_dump(mode="json"))},
            },
        )
