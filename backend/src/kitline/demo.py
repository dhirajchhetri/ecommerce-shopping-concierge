"""Run one concierge request from the command line."""

from __future__ import annotations

import sys

from kitline.config import Settings
from kitline.runtime import build_service

DEFAULT_REQUEST = (
    "I need a laptop for video editing, a monitor, and a two-year warranty. Budget $2,500."
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    text = " ".join(args).strip() or DEFAULT_REQUEST
    service = build_service(Settings())
    session = service.create_session()
    result = service.converse(session.session_id, text, budget_cents=None)
    print(result.model_dump_json(indent=2))
    return 0 if result.status == "validated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
