"""
Read-only Prisma queries powering the subject-librarian review surface
(plan Op 1). NO writes here -- this module only ever does find_many /
find_unique. The librarian workflow is: spot a wrong/questionable
answer, note its id + time, report it to the maintainer (who changes
backend behavior). Verdict-writing / corrections / digests are
deliberately out of scope for v1.

All functions are defensive: a query failure returns an empty
result, never raises into the endpoint -- a broken admin query must
degrade to "no rows", not 500 the page.

Schema fields used (verified against prisma/schema.prisma):
  Message(type, content, timestamp, conversationId, isPositiveRated,
          intent, scopeCampus, scopeLibrary, modelUsed, confidence,
          wasRefusal, refusalTrigger, citedChunkIds)
  Conversation(id, createdAt, updatedAt, toolUsed)
  ModelTokenUsage(llmModelName, promptTokens, completionTokens,
          totalTokens, cachedInputTokens, callSite, conversationId,
          createdAt)
  ToolExecution(agentName, toolName, success, executionTime,
          timestamp, conversationId)
  ConversationFeedback(rating, userComment, conversationId)

`isPositiveRated` is the thumbs signal: False = thumbs-DOWN (the
primary "questionable answer" trigger), True = up, None = unrated.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Recognized list filters. Anything else falls back to "flagged".
FILTERS = ("flagged", "thumbs_down", "thumbs_up", "refusal",
           "low_confidence", "rated", "reviewed", "all")


def _msg_dict(m: Any) -> dict:
    return {
        "id": getattr(m, "id", None),
        "role": getattr(m, "type", None),
        "content": getattr(m, "content", "") or "",
        "time": str(getattr(m, "timestamp", "") or ""),
        "intent": getattr(m, "intent", None),
        "scope_campus": getattr(m, "scopeCampus", None),
        "scope_library": getattr(m, "scopeLibrary", None),
        "model_used": getattr(m, "modelUsed", None),
        "confidence": getattr(m, "confidence", None),
        "was_refusal": bool(getattr(m, "wasRefusal", False)),
        "refusal_trigger": getattr(m, "refusalTrigger", None),
        "is_positive_rated": getattr(m, "isPositiveRated", None),
        "cited_chunk_ids": list(getattr(m, "citedChunkIds", []) or []),
    }


async def list_flagged(
    db: Any,
    *,
    filter_preset: str = "flagged",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return summary rows of MESSAGES that warrant a librarian look.

    `flagged` (default) = thumbs-down OR a refusal OR low confidence
    -- the union a reviewer cares about. Newest first. Each row is
    enough for the list view; full drill-down is `conversation_detail`.
    """
    where: dict
    fp = filter_preset if filter_preset in FILTERS else "flagged"
    if fp == "thumbs_down":
        where = {"isPositiveRated": False}
    elif fp == "thumbs_up":
        # Positive ratings were unreachable before 2026-07-27: the data
        # was there (Message.isPositiveRated=True) but no preset queried
        # it, so "what is the bot getting RIGHT" had no surface.
        where = {"isPositiveRated": True}
    elif fp == "refusal":
        where = {"wasRefusal": True}
    elif fp == "low_confidence":
        where = {"confidence": "low"}
    elif fp == "reviewed":
        where = {"NOT": [{"reviewedAt": None}]}
    elif fp == "rated":
        # Turns in a conversation the patron left a star rating on.
        # Conversation-scoped signal projected onto message rows --
        # resolved after the query (see _rated_conversation_ids).
        where = {"type": "assistant"}
    elif fp == "all":
        where = {}
    else:  # flagged: the union reviewers actually want
        where = {
            "OR": [
                {"isPositiveRated": False},
                {"wasRefusal": True},
                {"confidence": "low"},
            ]
        }
    # Handled rows drop out of every working view except the explicit
    # "reviewed" and "all" tabs -- otherwise the queue never shrinks and
    # a reviewer can't tell fresh from already-triaged.
    if fp not in ("reviewed", "all"):
        where = {"AND": [where, {"reviewedAt": None}]} if where else {"reviewedAt": None}
    try:
        rows = await db.message.find_many(
            where=where,
            order={"timestamp": "desc"},
            take=max(1, min(limit, 200)),
            skip=max(0, offset),
        )
    except Exception as e:  # noqa: BLE001 -- admin query must not 500
        logger.warning("list_flagged query failed: %s", e)
        return []
    return [
        {
            "message_id": getattr(m, "id", None),
            "conversation_id": getattr(m, "conversationId", None),
            "time": str(getattr(m, "timestamp", "") or ""),
            "role": getattr(m, "type", None),
            "preview": (getattr(m, "content", "") or "")[:240],
            "intent": getattr(m, "intent", None),
            "was_refusal": bool(getattr(m, "wasRefusal", False)),
            "refusal_trigger": getattr(m, "refusalTrigger", None),
            "confidence": getattr(m, "confidence", None),
            "is_positive_rated": getattr(m, "isPositiveRated", None),
            "reviewed_at": (
                str(getattr(m, "reviewedAt", "") or "") or None
            ),
        }
        for m in (rows or [])
    ]


async def attach_feedback(db: Any, rows: list[dict]) -> list[dict]:
    """Annotate list rows with their conversation's patron star rating.

    The star rating + comment ("rate this conversation") lives on
    ConversationFeedback, keyed by conversation -- so before 2026-07-27
    the only way to find a rated conversation was to open rows one at a
    time and hope. One batched query per page adds `feedback_rating` /
    `feedback_comment` so the list can show them inline.

    Never raises: on a DB error the rows come back unannotated.
    """
    conv_ids = list({r.get("conversation_id") for r in rows
                     if r.get("conversation_id")})
    if not conv_ids:
        return rows
    try:
        fbs = await db.conversationfeedback.find_many(
            where={"conversationId": {"in": conv_ids}}
        )
    except Exception as e:  # noqa: BLE001 -- annotation is garnish
        logger.warning("attach_feedback failed: %s", e)
        return rows
    by_conv = {
        getattr(f, "conversationId", None): f for f in (fbs or [])
    }
    for r in rows:
        f = by_conv.get(r.get("conversation_id"))
        r["feedback_rating"] = getattr(f, "rating", None) if f else None
        r["feedback_comment"] = getattr(f, "userComment", None) if f else None
    return rows


async def mark_reviewed(
    db: Any, message_id: str, *, reviewed_by: str = "operator",
    undo: bool = False,
) -> bool:
    """Flip one queue row's triage state. Returns True on success.

    Idempotent by construction: setting an already-set value is a no-op
    write. `undo` clears it so a mis-click is recoverable.
    """
    try:
        await db.message.update(
            where={"id": str(message_id)},
            data=(
                {"reviewedAt": None, "reviewedBy": None} if undo
                else {"reviewedAt": datetime.now(timezone.utc),
                      "reviewedBy": reviewed_by}
            ),
        )
        return True
    except Exception as e:  # noqa: BLE001 -- admin action must not 500
        logger.warning("mark_reviewed(%s) failed: %s", message_id, e)
        return False


async def conversation_detail(db: Any, conversation_id: str) -> Optional[dict]:
    """Full read-only drill-down for one conversation: id, time, the
    whole transcript, token usage, tools called, human-handoff, and
    the ultimate outcome. Returns None if not found / on error."""
    if not conversation_id:
        return None
    try:
        conv = await db.conversation.find_unique(
            where={"id": str(conversation_id)}
        )
        if conv is None:
            return None
        msgs = await db.message.find_many(
            where={"conversationId": str(conversation_id)},
            order={"timestamp": "asc"},
        )
        toks = await db.modeltokenusage.find_many(
            where={"conversationId": str(conversation_id)},
            order={"createdAt": "asc"},
        )
        tools = await db.toolexecution.find_many(
            where={"conversationId": str(conversation_id)},
            order={"timestamp": "asc"},
        )
        fb = await db.conversationfeedback.find_unique(
            where={"conversationId": str(conversation_id)}
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "conversation_detail(%s) failed: %s", conversation_id, e
        )
        return None

    messages = [_msg_dict(m) for m in (msgs or [])]
    # Human-handoff: any turn whose refusal trigger routes to a person.
    handoff_triggers = {
        "human_handoff", "capability_limit", "live_data_down",
        "staff_privacy",
    }
    handoff = [
        {"message_id": m["id"], "time": m["time"],
         "trigger": m["refusal_trigger"]}
        for m in messages
        if m["was_refusal"] and (m["refusal_trigger"] in handoff_triggers)
    ]
    last_assistant = next(
        (m for m in reversed(messages) if m["role"] == "assistant"), None
    )
    token_rows = [
        {
            "model": getattr(t, "llmModelName", None),
            "call_site": getattr(t, "callSite", None),
            "prompt": getattr(t, "promptTokens", 0),
            "cached_input": getattr(t, "cachedInputTokens", 0),
            "completion": getattr(t, "completionTokens", 0),
            "total": getattr(t, "totalTokens", 0),
            "time": str(getattr(t, "createdAt", "") or ""),
        }
        for t in (toks or [])
    ]
    return {
        "conversation_id": str(conversation_id),
        "created_at": str(getattr(conv, "createdAt", "") or ""),
        "updated_at": str(getattr(conv, "updatedAt", "") or ""),
        "tools_used_summary": list(getattr(conv, "toolUsed", []) or []),
        "messages": messages,
        "token_usage": token_rows,
        "token_total": sum(r["total"] or 0 for r in token_rows),
        "tools_called": [
            {
                "agent": getattr(t, "agentName", None),
                "tool": getattr(t, "toolName", None),
                "success": bool(getattr(t, "success", False)),
                "ms": getattr(t, "executionTime", 0),
                "time": str(getattr(t, "timestamp", "") or ""),
            }
            for t in (tools or [])
        ],
        "human_handoff": handoff,
        "outcome": {
            "final_answer": (last_assistant or {}).get("content"),
            "was_refusal": (last_assistant or {}).get("was_refusal"),
            "refusal_trigger": (last_assistant or {}).get("refusal_trigger"),
            "confidence": (last_assistant or {}).get("confidence"),
        },
        "feedback": (
            None if fb is None else {
                "rating": getattr(fb, "rating", None),
                "comment": getattr(fb, "userComment", None),
            }
        ),
    }


__all__ = ["FILTERS", "attach_feedback", "conversation_detail",
           "list_flagged", "mark_reviewed"]
