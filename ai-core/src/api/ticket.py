"""
API endpoint for creating LibAnswers support tickets.
Uses the LibAnswers API v1.1 POST /ticket/create endpoint.

Ref: https://libanswers.lib.miamioh.edu/admin/widget/api/1.1
"""

import os
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ticket"])

# LibAnswers credentials from .env
LIBANS_CLIENT_ID = os.getenv("LIBANS_CLIENT_ID", "")
LIBANS_CLIENT_SECRET = os.getenv("LIBANS_CLIENT_SECRET", "")
LIBANS_OAUTH_URL = os.getenv("LIBANS_OAUTH_URL", "")
LIBANS_QUEUE_ID = os.getenv("LIBANS_QUEUE_ID", "")

# Derive API base URL from OAuth URL (strip /oauth/token, keep base)
# e.g. https://libanswers.lib.miamioh.edu/api/1.1/oauth/token -> https://libanswers.lib.miamioh.edu/api/1.1
LIBANS_API_BASE = LIBANS_OAUTH_URL.replace("/oauth/token", "").rstrip("/") if LIBANS_OAUTH_URL else ""


class TicketCreateRequest(BaseModel):
    """Request model matching the frontend form fields."""
    question: str
    details: Optional[str] = ""
    name: Optional[str] = ""
    email: Optional[str] = ""
    ua: Optional[str] = ""


class TicketCreateResponse(BaseModel):
    """Response model for ticket creation."""
    success: bool
    ticketId: Optional[str] = None
    error: Optional[str] = None


async def _get_libanswers_token() -> str:
    """Get OAuth access token from LibAnswers."""
    if not all([LIBANS_CLIENT_ID, LIBANS_CLIENT_SECRET, LIBANS_OAUTH_URL]):
        raise ValueError("LibAnswers OAuth credentials not configured (LIBANS_CLIENT_ID, LIBANS_CLIENT_SECRET, LIBANS_OAUTH_URL)")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            LIBANS_OAUTH_URL,
            data={
                "client_id": LIBANS_CLIENT_ID,
                "client_secret": LIBANS_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        )

        if response.status_code != 200:
            raise ValueError(f"LibAnswers OAuth failed: HTTP {response.status_code}")

        data = response.json()
        token = data.get("access_token")
        if not token:
            raise ValueError("LibAnswers OAuth response missing access_token")
        return token


@router.post("/ticket/create", response_model=TicketCreateResponse)
async def create_ticket(request: TicketCreateRequest):
    """
    Create a support ticket in LibAnswers.

    Maps frontend fields to LibAnswers API parameters:
      - question -> pquestion (max 150 chars, required)
      - details  -> pdetails
      - name     -> pname
      - email    -> pemail
      - ua       -> ua

    Requires LIBANS_QUEUE_ID to be set in .env.
    """
    if not LIBANS_QUEUE_ID:
        raise HTTPException(status_code=500, detail="LIBANS_QUEUE_ID not configured")

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")

    try:
        token = await _get_libanswers_token()

        # Build form-urlencoded payload per LibAnswers API spec
        payload = {
            "quid": LIBANS_QUEUE_ID,
            "pquestion": request.question[:150],
        }
        if request.details:
            payload["pdetails"] = request.details
        if request.name:
            payload["pname"] = request.name
        if request.email:
            payload["pemail"] = request.email
        if request.ua:
            payload["ua"] = request.ua

        ticket_url = f"{LIBANS_API_BASE}/ticket/create"
        logger.info(f"🎫 [Ticket] Creating ticket | queue={LIBANS_QUEUE_ID} | question={request.question[:60]}...")

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                ticket_url,
                headers={
                    "Authorization": f"Bearer {token}",
                },
                data=payload,  # application/x-www-form-urlencoded
            )

        result = response.json()

        if response.status_code in (200, 201) and not result.get("error"):
            ticket_id = str(result.get("ticketId", "") or result.get("ticketUrl", ""))
            logger.info(f"✅ [Ticket] Created successfully | ticket={ticket_id}")
            return TicketCreateResponse(success=True, ticketId=ticket_id)
        else:
            error_msg = result.get("error", f"HTTP {response.status_code}")
            logger.error(f"❌ [Ticket] LibAnswers error: {error_msg}")
            raise HTTPException(status_code=response.status_code, detail=error_msg)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Ticket] Failed to create ticket: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create ticket: {str(e)}")
