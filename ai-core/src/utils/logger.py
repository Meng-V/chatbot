"""Logging utility for agent actions."""
import logging
from typing import Any, Dict
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

class AgentLogger:
    """Logger for tracking agent and tool usage."""
    
    def __init__(self):
        self.logs = []
    
    def log(self, message: str, metadata: Dict[str, Any] = None):
        """Log a message with optional metadata."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "metadata": metadata or {}
        }
        self.logs.append(log_entry)
        
        # Print to console with emoji formatting
        console_msg = message
        if metadata:
            console_msg += f" {metadata}"
        logger.info(console_msg)
    
    def get_logs(self) -> list:
        """Get all logged entries."""
        return self.logs
    
    def clear(self):
        """Clear all logs."""
        self.logs = []
