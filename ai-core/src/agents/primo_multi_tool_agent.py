"""Primo Agent - Library catalog search (stub implementation)."""


class PrimoAgent:
    """Agent for searching library catalog via Primo API.
    
    This is a stub implementation - Primo API integration not yet configured.
    """
    
    def __init__(self):
        self.name = "Primo Catalog Search"
    
    async def execute(self, query: str, **kwargs) -> dict:
        """Search the library catalog (stub - returns helpful message)."""
        return {
            "text": f"To search for '{query}', please use our library catalog directly at https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU&lang=en&mode=basic. "
                    f"You can search for books, articles, journals, and other materials there.",
            "success": True,
            "source": "primo_stub"
        }
