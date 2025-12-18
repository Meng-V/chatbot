"""
Comprehensive Logging Configuration

Sets up structured logging for the entire application with:
- File rotation
- Different log levels
- Structured JSON logging
- Error tracking
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler


# Log directory
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Log files
APP_LOG_FILE = LOG_DIR / "app.log"
ERROR_LOG_FILE = LOG_DIR / "errors.log"
AGENT_LOG_FILE = LOG_DIR / "agents.log"
API_LOG_FILE = LOG_DIR / "api.log"


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data
        
        return json.dumps(log_data)


def setup_logging():
    """Configure logging for the entire application."""
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Console handler (human-readable)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # App log file (rotating, JSON format)
    app_handler = RotatingFileHandler(
        APP_LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(app_handler)
    
    # Error log file (rotating, JSON format)
    error_handler = RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(error_handler)
    
    # Agent log file (rotating, JSON format)
    agent_logger = logging.getLogger("agent")
    agent_handler = RotatingFileHandler(
        AGENT_LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    agent_handler.setLevel(logging.INFO)
    agent_handler.setFormatter(JSONFormatter())
    agent_logger.addHandler(agent_handler)
    
    # API log file (rotating, JSON format)
    api_logger = logging.getLogger("api")
    api_handler = RotatingFileHandler(
        API_LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    api_handler.setLevel(logging.INFO)
    api_handler.setFormatter(JSONFormatter())
    api_logger.addHandler(api_handler)
    
    logging.info("✅ Logging system initialized")
    logging.info(f"   App log: {APP_LOG_FILE}")
    logging.info(f"   Error log: {ERROR_LOG_FILE}")
    logging.info(f"   Agent log: {AGENT_LOG_FILE}")
    logging.info(f"   API log: {API_LOG_FILE}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module."""
    return logging.getLogger(name)
