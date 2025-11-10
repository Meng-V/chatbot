"""Citation assistance tool with comprehensive style support."""
from typing import Dict, Any
from src.tools.base import Tool

# Citation style URL mappings
CITATION_STYLES = {
    "APA": {
        "General Reference": "https://libguides.lib.miamioh.edu/citation/apa",
        "In-text Citations": "https://libguides.lib.miamioh.edu/citation/apa_in-text_citations",
        "Example Citations-Print": "https://libguides.lib.miamioh.edu/citation/apa_print-examples",
        "Example Citations-Online,Electronic": "https://libguides.lib.miamioh.edu/citation/apa_electronic-examples",
        "Example Citations-Images,Video,Audio": "https://libguides.lib.miamioh.edu/citation/apa_multimedia-examples",
        "Example Citations-Business Database": "https://libguides.lib.miamioh.edu/citation/apa_business-examples",
        "Paper Format": "https://libguides.lib.miamioh.edu/c.php?g=320744&p=9188521",
    },
    "MLA": {
        "General Reference": "https://libguides.lib.miamioh.edu/citation/mla",
        "In-text Citations": "https://libguides.lib.miamioh.edu/citation/mla_in-text_citations",
        "Example Citations-Print": "https://libguides.lib.miamioh.edu/citation/mla_print-examples",
        "Example Citations-Online,Electronic": "https://libguides.lib.miamioh.edu/citation/ama_online",
        "Example Citations-Images,Video,Audio": "https://libguides.lib.miamioh.edu/citation/mla_multimedia-examples",
        "Example Citations-Business Database": "https://libguides.lib.miamioh.edu/citation/mla_business",
        "Handbook": "https://libguides.lib.miamioh.edu/citation/mla_business",
    },
    "Chicago": {
        "General Reference": "https://libguides.lib.miamioh.edu/citation/chicago",
        "In-text Citations": "https://libguides.lib.miamioh.edu/citation/chicago_in-text_citations",
        "In-text Citations-AuthorDate": "https://libguides.lib.miamioh.edu/citation/chicago_in-text_author-date",
        "Example Citations-Print": "https://libguides.lib.miamioh.edu/citation/chicago_print-examples",
        "Example Citations-Online,Electronic": "https://libguides.lib.miamioh.edu/citation/chicago_electronic-examples",
        "Example Citations-Images,Video,Audio": "https://libguides.lib.miamioh.edu/citation/chicago_multimedia-examples",
    },
    "Turabian": {
        "General Reference": "https://libguides.lib.miamioh.edu/citation/chicago",
        "In-text Citations": "https://libguides.lib.miamioh.edu/citation/chicago_in-text_citations",
        "In-text Citations-AuthorDate": "https://libguides.lib.miamioh.edu/citation/chicago_in-text_author-date",
        "Example Citations-Print": "https://libguides.lib.miamioh.edu/citation/chicago_print-examples",
        "Example Citations-Online,Electronic": "https://libguides.lib.miamioh.edu/citation/chicago_electronic-examples",
        "Example Citations-Images,Video,Audio": "https://libguides.lib.miamioh.edu/citation/chicago_multimedia-examples",
    },
    "AMA": {
        "General Reference": "https://libguides.lib.miamioh.edu/citation/ama",
        "In-text Citations": "https://libguides.lib.miamioh.edu/citation/chicago_in-text_citations",
        "In-text Citations-AuthorDate": "https://libguides.lib.miamioh.edu/citation/chicago_in-text_author-date",
        "Example Citations-Print": "https://libguides.lib.miamioh.edu/citation/chicago_print-examples",
        "Example Citations-Online,Electronic": "https://libguides.lib.miamioh.edu/citation/chicago_electronic-examples",
        "Example Citations-Images,Video,Audio": "https://libguides.lib.miamioh.edu/citation/chicago_multimedia-examples",
    },
}

class CitationAssistTool(Tool):
    """Citation assistance for multiple styles."""
    
    @property
    def name(self) -> str:
        return "citation_assist"
    
    @property
    def description(self) -> str:
        return "Get citation help for APA, MLA, Chicago, Turabian, or AMA styles"
    
    async def execute(
        self,
        query: str,
        log_callback=None,
        citation_type: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Provide citation resources."""
        try:
            if not citation_type:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Please specify a citation style: APA, MLA, Chicago, Turabian, or AMA."
                }
            
            # Normalize citation type
            citation_type = citation_type.upper().strip()
            
            if citation_type not in CITATION_STYLES:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"Invalid citation style '{citation_type}'. Supported styles: APA, MLA, Chicago, Turabian, AMA."
                }
            
            if log_callback:
                log_callback(f"📖 [Citation Assist Tool] Providing {citation_type} citation help")
            
            # Get links for this style
            links = CITATION_STYLES[citation_type]
            
            # Format response
            text = f"**{citation_type} Citation Help:**\n\n"
            
            for category, url in links.items():
                text += f"• **{category}**: {url}\n"
            
            text += "\n**Citation Managers:**\n"
            text += "Consider using citation management tools for easier citation:\n"
            text += "• **Zotero** - Free, open-source\n"
            text += "• **Mendeley** - Free with collaboration features\n"
            text += "• **EndNote** - Comprehensive (paid)\n\n"
            text += "Learn more: https://libguides.lib.miamioh.edu/CitationManagers"
            
            if log_callback:
                log_callback(f"✅ [Citation Assist Tool] Provided {len(links)} resources")
            
            return {
                "tool": self.name,
                "success": True,
                "text": text,
                "citation_type": citation_type,
                "links": links
            }
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [Citation Assist Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Error getting citation help. Visit https://libguides.lib.miamioh.edu/citation"
            }
