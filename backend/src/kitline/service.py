"""Concierge service: agent attempts, validation, fallback, and session memory."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import date, datetime, timezone

from strands import Agent
from strands.types.exceptions import StructuredOutputException

from kitline.catalog import Catalog
from kitline.schemas import (
    BundleProposal,
    ConverseResponse,
    PackageOut,
    SessionOut,
    TurnOut,
)
from kitline.selection import build_fallback, parse_intent
from kitline.sessions import SessionStore
from kitline.stub_model import StubModel
from kitline.tools import SYSTEM_PROMPT, build_tools
from kitline.validator import validate_bundle

logger = logging.getLogger(__name__)


class SessionNotFound(KeyError):
    pass


def new_session_id() -> str:
    return "ses_" + uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def render_prompt(
    message: str,
    budget_cents: int | None,
    previous: PackageOut | None,
    errors: list[str],
) -> str:
    lines: list[str] = []
    if budget_cents is not None:
        lines.append(f"BUDGET_CENTS: {budget_cents}")
    if previous is not None:
        lines.append("PREVIOUS_PACKAGE: " + previous.model_dump_json())
        lines.append("The shopper already has a package. Adjust it to the new request.")
    lines.append("SHOPPER_MESSAGE:")
    lines.append(message.strip())
    if errors:
        lines.append("VALIDATION_FAILED")
        lines.append("The previous package was rejected:")
        lines.extend(f"- {error}" for error in errors)
        lines.append("Submit a corrected package. Use only SKUs the tools returned.")
    return "\n".join(lines)


class ConciergeService:
    def __init__(
        self,
        catalog: Catalog,
        sessions: SessionStore,
        model: StubModel | object,
        *,
        max_attempts: int = 2,
        clock: Callable[[], date] | None = None,
    ) -> None:
        self.catalog = catalog
        self.sessions = sessions
        self.model = model
        self.max_attempts = max_attempts
        self.clock = clock or date.today

    def create_session(self) -> SessionOut:
        now = _now()
        record = SessionOut(session_id=new_session_id(), created_at=now, updated_at=now, turns=[])
        self.sessions.put(record)
        return record

    def get_session(self, session_id: str) -> SessionOut:
        record = self.sessions.get(session_id)
        if record is None:
            raise SessionNotFound(session_id)
        return record

    def converse(self, session_id: str, message: str, budget_cents: int | None) -> ConverseResponse:
        record = self.get_session(session_id)
        previous = self._last_package(record)
        resolved_budget = budget_cents
        if resolved_budget is None:
            resolved_budget = parse_intent(message).budget_cents
        errors: list[str] = []
        tools_used: list[str] = []
        for attempt in range(1, self.max_attempts + 1):
            prompt = render_prompt(message, resolved_budget, previous, errors)
            proposal, schema_errors, tools_used = self._invoke(prompt)
            if proposal is None:
                errors = schema_errors or ["The model did not return a package."]
                logger.info("attempt=%s schema_rejected=%s", attempt, errors)
                continue
            outcome = validate_bundle(proposal, self.catalog, budget_cents=resolved_budget, today=self.clock())
            if outcome.ok and outcome.package is not None:
                return self._finish(
                    record,
                    message,
                    status="validated",
                    source="agent",
                    attempts=attempt,
                    message_text=outcome.package.summary,
                    package=outcome.package,
                    tools_used=tools_used,
                )
            errors = outcome.errors
            logger.info("attempt=%s rejected=%s", attempt, errors)

        fallback = build_fallback(
            self.catalog,
            message,
            resolved_budget,
            self.clock(),
            previous_categories=self._categories(previous),
        )
        if fallback is not None:
            outcome = validate_bundle(fallback, self.catalog, budget_cents=resolved_budget, today=self.clock())
            if outcome.ok and outcome.package is not None:
                return self._finish(
                    record,
                    message,
                    status="validated",
                    source="fallback",
                    attempts=self.max_attempts,
                    message_text=(
                        "The drafted package did not pass the checks, so this is a simpler one that did. "
                        + outcome.package.summary
                    ),
                    package=outcome.package,
                    tools_used=tools_used,
                )
        return self._finish(
            record,
            message,
            status="unfulfilled",
            source="fallback",
            attempts=self.max_attempts,
            message_text="Nothing in the catalog fits that request and budget.",
            package=None,
            tools_used=tools_used,
        )

    def _invoke(self, prompt: str) -> tuple[BundleProposal | None, list[str], list[str]]:
        agent = Agent(
            model=self.model,
            tools=build_tools(self.catalog, self.clock),
            system_prompt=SYSTEM_PROMPT,
            callback_handler=None,
        )
        try:
            result = agent(prompt, structured_output_model=BundleProposal)
        except StructuredOutputException as exc:
            return None, [f"The package did not match the schema: {exc}"], []
        names: list[str] = []
        for message in agent.messages:
            for block in message.get("content", []):
                tool_use = block.get("toolUse")
                if tool_use:
                    names.append(tool_use["name"])
        proposal = result.structured_output
        if not isinstance(proposal, BundleProposal):
            return None, ["The model did not return a package."], names
        return proposal, [], names

    def _finish(
        self,
        record: SessionOut,
        shopper_text: str,
        *,
        status: str,
        source: str,
        attempts: int,
        message_text: str,
        package: PackageOut | None,
        tools_used: list[str],
    ) -> ConverseResponse:
        now = _now()
        record.turns.append(TurnOut(role="user", text=shopper_text, created_at=now))
        record.turns.append(
            TurnOut(
                role="assistant",
                text=message_text,
                created_at=now,
                package=package,
                status=status,  # type: ignore[arg-type]
                source=source,  # type: ignore[arg-type]
                attempts=attempts,
            )
        )
        record.updated_at = now
        self.sessions.put(record)
        return ConverseResponse(
            session_id=record.session_id,
            status=status,  # type: ignore[arg-type]
            source=source,  # type: ignore[arg-type]
            attempts=attempts,
            message=message_text,
            package=package,
            tools_used=tools_used,
            turns=record.turns,
        )

    @staticmethod
    def _last_package(record: SessionOut) -> PackageOut | None:
        for turn in reversed(record.turns):
            if turn.package is not None:
                return turn.package
        return None

    @staticmethod
    def _categories(package: PackageOut | None) -> list[str] | None:
        if package is None:
            return None
        categories: list[str] = []
        for line in package.lines:
            if line.role == "warranty" or line.category in categories:
                continue
            categories.append(line.category)
        return categories
