"""LibChat Agent for human librarian handoff with availability checking."""
from typing import Dict, Any
import re
from src.api.askus_hours import get_askus_hours_for_date

LIBCHAT_WIDGET_URL = "https://www.lib.miamioh.edu/research/research-support/ask/"
TICKET_URL = "https://www.lib.miamioh.edu/research/research-support/ask/"

async def ticket_request_handler(query: str, log_callback=None) -> Dict[str, Any]:
    """Handle explicit ticket submission requests."""
    if log_callback:
        log_callback("🎫 [Ticket Handler] User explicitly requested to submit a ticket")
    
    try:
        hours_data = await get_askus_hours_for_date()
        is_open = hours_data.get("is_open", False)
        current_period = hours_data.get("current_period")
        
        if is_open and current_period:
            if log_callback:
                log_callback("✅ [Ticket Handler] Librarians are available, but user wants to submit ticket")
            return {
                "source": "TicketRequest",
                "success": True,
                "needs_human": False,
                "is_available": True,
                "text": (
                    f"For additional help, visit:\n"
                    f"{TICKET_URL}\n\n"
                    f"💡 **Note**: Librarians are currently available (until {current_period['close']})."
                )
            }
        else:
            if log_callback:
                log_callback("⏰ [Ticket Handler] Librarians offline, guiding to ticket submission")
            return {
                "source": "TicketRequest",
                "success": True,
                "needs_human": False,
                "is_available": False,
                "text": (
                    f"For additional help, visit:\n"
                    f"{TICKET_URL}\n\n"
                    f"A librarian will respond to your request."
                )
            }
    
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ [Ticket Handler] Error: {str(e)}")
        return {
            "source": "TicketRequest",
            "success": True,
            "needs_human": False,
            "text": (
                f"For additional help, visit:\n"
                f"{TICKET_URL}"
            )
        }


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
                    f"💡 **Tip:** Use the **Copy Transcript** or **AI Summary** button on the next screen to save our conversation to your clipboard. "
                    f"You can then paste it to the librarian so they have full context."
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
                    f"⏰ **Currently closed**\n"
                    f"Hours today: {next_open} - {next_close}\n\n"
                    f"For help, visit: {TICKET_URL}"
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
                    f"⏰ **Not available today**\n\n"
                    f"For help, visit: {TICKET_URL}\n\n"
                    f"Or call: **(513) 529-4141**"
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
                f"For help, visit: {LIBCHAT_WIDGET_URL}\n"
                f"Or call: **(513) 529-4141**"
            )
        }
