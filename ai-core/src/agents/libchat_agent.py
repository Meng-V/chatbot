"""LibChat Agent for human librarian handoff."""
from typing import Dict, Any

LIBCHAT_WIDGET_URL = "https://www.lib.miamioh.edu/research/research-support/ask/"

async def libchat_handoff(query: str, log_callback=None) -> Dict[str, Any]:
    """Escalate to human librarian via LibChat."""
    if log_callback:
        log_callback("👤 [LibChat Agent] Initiating human handoff")
    return {
        "source": "LibChat",
        "success": True,
        "needs_human": True,
        "text": f"Sorry I can't answer this type of questions. I'll connect you with a librarian who can help better.\n\nClick here to chat: {LIBCHAT_WIDGET_URL}"
    }
