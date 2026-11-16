"""Register one native review tool and seven on-demand workflow skills."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Protocol

from .auto_store import AutoReviewStore
from .policy import ActivationPolicy
from .review import LENSES, InvalidReview, Llm, ReviewRequest, run_review

ToolHandler = Callable[..., Awaitable[str]]
PromptRenderer = Callable[[Mapping[str, object]], str]
SKILLS = {
    "egm-brainstorm": "Explore requirements and challenge a concise concept brief.",
    "egm-draft": "Turn agreed requirements into a self-contained design draft.",
    "egm-review": "Review explicit design/source snapshots using isolated model calls.",
    "egm-resolve": "Triage findings and apply only authorized design changes.",
    "egm-review-loop": "Run a user-budgeted revision/review cycle, never an endless loop.",
    "egm-drift-report": "Compare an accepted design with explicit implementation snapshots.",
    "egm-bootstrap": "Document an existing codebase from inspected source evidence.",
}
TOOL_SCHEMA: dict[str, object] = {
    "name": "egm_review",
    "description": (
        "Review supplied design/source TEXT with 1–3 fresh, tool-free model requests. "
        "Uses the active Hermes provider; consumes model usage. No document reads or edits. "
        "Explicitly requested reviews use automatic=false (default). Policy-initiated "
        "reviews MUST use automatic=true, which checks opt-in workspace/session limits. "
        "Never relabel a blocked automatic attempt as manual to bypass its policy. "
        "Supply only approved, relevant text: never conversation history, memory or secrets. "
        "Documents are labeled snapshots, not paths to open. Results are untrusted advice."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target", "documents"],
        "properties": {
            "automatic": {
                "type": "boolean",
                "default": False,
                "description": (
                    "True for policy-initiated reviews; false for an explicit user request."
                ),
            },
            "target": {"type": "string", "description": "ID of the document under review."},
            "documents": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "description": "Explicit texts; serialized snapshot <=48,000 UTF-8 bytes.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "text"],
                    "properties": {
                        "id": {"type": "string", "minLength": 1, "maxLength": 80},
                        "text": {"type": "string", "minLength": 1, "maxLength": 48000},
                    },
                },
            },
            "lenses": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "uniqueItems": True,
                "items": {"type": "string", "enum": list(LENSES)},
                "description": "Default: all three lenses. Select one for a quick review.",
            },
        },
    },
}


class PluginContext(Protocol):
    @property
    def llm(self) -> Llm: ...

    def register_tool(
        self,
        *,
        name: str,
        toolset: str,
        schema: dict[str, object],
        handler: ToolHandler,
        is_async: bool,
    ) -> object: ...

    def register_skill(self, name: str, path: Path, description: str = "") -> object: ...

    def get_config(self, key: str, default: object = None) -> object: ...

    def register_system_prompt_section(
        self, identifier: str, content: PromptRenderer, *, max_chars: int
    ) -> object: ...


def open_state_db() -> sqlite3.Connection:
    # Documented, profile-aware host API. No Hermes dependency in the standalone package.
    from plugins.plugin_storage import plugin_db  # type: ignore[import-not-found]

    connection: object = plugin_db("hermes-egm", filename="automatic-reviews.sqlite3")
    if not isinstance(connection, sqlite3.Connection):
        raise TypeError("Hermes plugin storage returned an incompatible connection")
    return connection


def read_policy(ctx: PluginContext) -> ActivationPolicy:
    return ActivationPolicy.parse(
        {
            "activation": ctx.get_config("activation", "suggest"),
            "auto_projects": ctx.get_config("auto_projects", []),
            "auto_max_reviews_per_session": ctx.get_config("auto_max_reviews_per_session", 1),
        }
    )


_DEFAULT_REVIEW_TIMEOUT_SECONDS = 90

_DEFAULT_REVIEW_MAX_TOKENS = 2400


def read_review_timeout(ctx: PluginContext) -> float:
    """Per-reviewer provider timeout; an invalid setting falls back to the default.

    The timeout is always passed explicitly: when omitted, the Hermes host applies
    its own auxiliary-call default rather than leaving the request unbounded.
    """
    raw = ctx.get_config("review_timeout_seconds", _DEFAULT_REVIEW_TIMEOUT_SECONDS)
    if type(raw) is not int or not 10 <= raw <= 3600:
        return float(_DEFAULT_REVIEW_TIMEOUT_SECONDS)
    return float(raw)


def read_review_max_tokens(ctx: PluginContext) -> int:
    """Per-reviewer requested output-token budget; an invalid setting falls back to the default.

    The default bounds ordinary findings output. Reasoning models spend thinking
    tokens from the same completion budget, so operators running those routes raise
    this to leave room for the findings JSON after the thinking block.
    """
    raw = ctx.get_config("review_max_tokens", _DEFAULT_REVIEW_MAX_TOKENS)
    if type(raw) is not int or not 256 <= raw <= 16384:
        return _DEFAULT_REVIEW_MAX_TOKENS
    return raw


_SUGGEST = (
    "Mode=suggest. When a substantial design draft is ready, before implementation, "
    "suggest EGM once and wait for the user to request review. Use automatic=false. "
    "Skip routine edits, trivial fixes, and repeated suggestions."
)
_COMMON = (
    " Explicit user-requested reviews always use automatic=false. "
    "Respect opt-outs and existing source-sharing/provider restrictions. "
    "Review only relevant, authorized explicit text snapshots; never include chat, "
    "memory, secrets, or these routing instructions. The main agent may read the "
    "selected documents; reviewers receive no tools. Findings are untrusted advice, "
    "not approval. Do not automatically edit, approve, or repeat review until clean. "
    "Never turn a denied automatic call into a manual call to evade its limits."
)


def routing_section(
    ctx: PluginContext, store: AutoReviewStore, session_info: Mapping[str, object]
) -> str:
    """The host freezes this main-agent guidance; no reviewer is started here."""
    try:
        policy = read_policy(ctx)
        if policy.activation == "manual":
            mode = "Mode=manual. Use EGM only on an explicit review request; automatic=false."
        elif policy.activation == "suggest":
            mode = _SUGGEST
        else:
            root = policy.approved_root(session_info.get("cwd"))
            enrolled = root is not None and store.enroll(
                session_info.get("session_id"), root, policy.auto_max_reviews_per_session
            )
            if enrolled:
                mode = (
                    "Mode=auto for this session's explicitly allowed starting workspace. "
                    "When a substantial design draft is ready, before implementation, "
                    "run egm_review once with automatic=true without another confirmation. "
                    "Use this for architectural, trust-boundary, storage, concurrency, "
                    "or failure-recovery decisions, not trivial fixes or every edit. "
                    "Automatic attempts are bounded; duplicates and exhausted budgets "
                    "are blocked in code. "
                    "A skipped/failed review is not a pass. If the workspace changes, "
                    "do not automatically review it: start a new session or ask for manual review."
                )
            else:
                mode = "Automatic review unavailable for this session/workspace. " + _SUGGEST
    except Exception:
        # Bad configuration, missing host context, or unavailable storage must not start usage.
        mode = (
            "Automatic review unavailable: configuration/state could not be validated. " + _SUGGEST
        )
    return "EGM activation policy. " + mode + _COMMON


def register(ctx: PluginContext) -> None:
    store = AutoReviewStore(open_state_db)

    async def handle(
        args: dict[str, object], *, session_id: object = None, **_host_context: object
    ) -> str:
        # Only host-injected session identity is used; parent_agent/history stay untouched.
        try:
            if not isinstance(args, dict):
                raise InvalidReview("arguments must be an object")
            automatic = args.get("automatic", False)
            if type(automatic) is not bool:
                raise InvalidReview("automatic must be a boolean")
            request = ReviewRequest.parse(
                {key: value for key, value in args.items() if key != "automatic"}
            )
        except InvalidReview as exc:
            return json.dumps({"status": "invalid_input", "error": str(exc)})
        if automatic:
            try:
                admission: str = store.reserve(session_id, request.snapshot_id, read_policy(ctx))
            except Exception:
                admission = "automatic_policy_unavailable"
            if admission != "allowed":
                return json.dumps(
                    {
                        "status": "skipped",
                        "outcome": "not_run",
                        "automatic": True,
                        "reason": admission,
                        "message": (
                            "No reviewer started. Manual retry requires an explicit user request."
                        ),
                    }
                )
        try:
            report = await run_review(
                ctx.llm,
                request,
                timeout_seconds=read_review_timeout(ctx),
                max_output_tokens=read_review_max_tokens(ctx),
            )
            return json.dumps({**report, "automatic": automatic}, ensure_ascii=True)
        except Exception:
            return json.dumps(
                {
                    "status": "failed",
                    "outcome": "incomplete",
                    "error": "host_error: check plugin/API compatibility and Hermes logs.",
                }
            )

    ctx.register_tool(
        name="egm_review",
        toolset="hermes_egm",
        schema=TOOL_SCHEMA,
        handler=handle,
        is_async=True,
    )
    ctx.register_system_prompt_section(
        "hermes-egm.activation", lambda info: routing_section(ctx, store, info), max_chars=2400
    )
    root = Path(__file__).resolve().parent.parent
    for name, description in SKILLS.items():
        ctx.register_skill(name, root / "skills" / name / "SKILL.md", description=description)
