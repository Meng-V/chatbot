"""LibChat Agent for human librarian handoff with availability checking."""
from typing import Dict, Any
from src.api.askus_hours import get_askus_hours_for_date

LIBCHAT_WIDGET_URL = "https://www.lib.miamioh.edu/research/research-support/ask/"
TICKET_URL = "https://www.lib.miamioh.edu/research/research-support/ask/"

async def libchat_handoff(query: str, log_callback=None) -> Dict[str, Any]:
    """Escalate to human librarian via LibChat with real-time availability check."""
    if log_callback:
        log_callback("👤 [LibChat Agent] Checking librarian availability")
    
    try:
        hours_data = await get_askus_hours_for_date()
        is_open = hours_data.get("is_open", False)
        current_period = hours_data.get("current_period")
        hours_list = hours_data.get("hours", [])
        
        if is_open and current_period:
            if log_callback:
                log_callback("✅ [LibChat Agent] Librarians are currently available")
            return {
                "source": "LibChat",
                "success": True,
                "needs_human": True,
                "is_available": True,
                "text": (
                    f"I'll connect you with a librarian who can help better.\n\n"
                    f"✅ **Librarians are available NOW** (until {current_period['close']})\n\n"
                    f"Click here to start a live chat: {LIBCHAT_WIDGET_URL}"
                )
            }
        
        elif hours_list and len(hours_list) > 0:
            next_open = hours_list[0].get("from")
            next_close = hours_list[0].get("to")
            if log_callback:
                log_callback(f"⏰ [LibChat Agent] Librarians available later: {next_open} - {next_close}")
            return {
                "source": "LibChat",
                "success": True,
                "needs_human": True,
                "is_available": False,
                "text": (
                    f"I'll help you get assistance from a librarian.\n\n"
                    f"⏰ **Live chat is currently closed**\n"
                    f"Chat hours today: {next_open} - {next_close}\n\n"
                    f"**Options:**\n"
                    f"• **Submit a ticket** for off-hours help: {TICKET_URL}\n"
                    f"• **Come back during chat hours** to talk to a librarian live"
                )
            }
        
        else:
            if log_callback:
                log_callback("📅 [LibChat Agent] No chat hours available today")
            return {
                "source": "LibChat",
                "success": True,
                "needs_human": True,
                "is_available": False,
                "text": (
                    f"I'll help you get assistance from a librarian.\n\n"
                    f"⏰ **Live chat is not available today**\n\n"
                    f"**Please submit a ticket** and a librarian will respond:\n"
                    f"{TICKET_URL}\n\n"
                    f"You can also contact us at **(513) 529-4141**"
                )
            }
    
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ [LibChat Agent] Error checking availability: {str(e)}")
        return {
            "source": "LibChat",
            "success": True,
            "needs_human": True,
            "is_available": None,
            "text": (
                f"I'll connect you with a librarian who can help better.\n\n"
                f"Visit our help page: {LIBCHAT_WIDGET_URL}\n"
                f"Or call us at **(513) 529-4141**"
            )
        }
