"""Base tool interface and registry."""
from typing import Protocol, Dict, Any, List, Callable, Optional
from abc import ABC, abstractmethod

class Tool(ABC):
    """Base tool interface."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """What this tool does."""
        pass
    
    @abstractmethod
    async def execute(self, query: str, **kwargs) -> Dict[str, Any]:
        """Execute the tool."""
        pass

class ToolRegistry:
    """Registry for all tools."""
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool):
        """Register a tool."""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all registered tools."""
        return list(self._tools.keys())

# Global registry
registry = ToolRegistry()

def register_tool(tool: Tool):
    """Register a tool in the global registry."""
    registry.register(tool)

def get_tool(name: str) -> Optional[Tool]:
    """Get a tool from the global registry."""
    return registry.get(name)
