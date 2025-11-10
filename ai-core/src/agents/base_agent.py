"""Base agent class."""
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
from src.tools.base import Tool

class Agent(ABC):
    """Base agent that contains multiple tools."""
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self._register_tools()
    
    @abstractmethod
    def _register_tools(self):
        """Register tools for this agent."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name."""
        pass
    
    @abstractmethod
    async def route_to_tool(self, query: str) -> str:
        """Decide which tool to use based on the query."""
        pass
    
    async def execute(self, query: str, log_callback=None, **kwargs) -> Dict[str, Any]:
        """Execute the agent by routing to the appropriate tool."""
        if log_callback:
            log_callback(f"🎯 [{self.name} Agent] Routing query to appropriate tool")
        
        # Route to specific tool
        tool_name = await self.route_to_tool(query)
        tool = self.tools.get(tool_name)
        
        if not tool:
            if log_callback:
                log_callback(f"❌ [{self.name} Agent] Tool '{tool_name}' not found")
            return {
                "agent": self.name,
                "tool": tool_name,
                "success": False,
                "error": f"Tool '{tool_name}' not registered"
            }
        
        if log_callback:
            log_callback(f"🔧 [{self.name} Agent] Using tool: {tool.name}")
        
        # Execute the tool
        result = await tool.execute(query, log_callback=log_callback, **kwargs)
        result["agent"] = self.name
        return result
    
    def register_tool(self, tool: Tool):
        """Register a tool with this agent."""
        self.tools[tool.name] = tool
    
    def list_tools(self) -> List[str]:
        """List all tools in this agent."""
        return list(self.tools.keys())
