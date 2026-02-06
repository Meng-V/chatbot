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


# Access log file (for HTTP request logs from uvicorn)
ACCESS_LOG_FILE = LOG_DIR / "access.log"


def setup_logging():
    """Configure logging for the entire application."""
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Console handler - WARNING+ only
    # (stdout/stderr is captured by systemd into /var/log/smartchatbot_backend/,
    #  so only warnings and errors should appear there)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # App log file (rotating, JSON format) - all INFO+ app logs
    app_handler = RotatingFileHandler(
        APP_LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(app_handler)
    
    # Error log file (rotating, JSON format) - ERROR+ only
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
    
    # --- Uvicorn logger routing ---
    # Route uvicorn access logs (HTTP requests) to access.log file
    # instead of letting them flood stdout/stderr -> /var/log/
    access_handler = RotatingFileHandler(
        ACCESS_LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=3
    )
    access_formatter = logging.Formatter(
        '%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    access_handler.setLevel(logging.INFO)
    access_handler.setFormatter(access_formatter)
    
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = []  # Remove default handlers
    uvicorn_access.addHandler(access_handler)
    uvicorn_access.propagate = False  # Don't send to root (prevents console + app.log spam)
    
    # Route uvicorn error logger: errors to file, warnings+ to console
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_error.handlers = []
    uvicorn_error.addHandler(app_handler)    # INFO+ to app.log
    uvicorn_error.addHandler(error_handler)  # ERROR+ to errors.log
    uvicorn_error.addHandler(console_handler)  # WARNING+ to console/systemd
    uvicorn_error.propagate = False
    
    # Route noisy third-party logs to access.log instead of console.
    # httpx/httpcore = HTTP client requests to OpenAI, Weaviate, Google, etc.
    # engineio/socketio = WebSocket PING/PONG heartbeat messages
    for noisy_logger_name in ["httpx", "httpcore", "urllib3", "engineio", "socketio", "websockets"]:
        noisy_logger = logging.getLogger(noisy_logger_name)
        noisy_logger.handlers = []
        noisy_logger.addHandler(access_handler)
        noisy_logger.propagate = False
    
    logging.info("✅ Logging system initialized")
    logging.info(f"   App log: {APP_LOG_FILE}")
    logging.info(f"   Error log: {ERROR_LOG_FILE}")
    logging.info(f"   Access log: {ACCESS_LOG_FILE}")
    logging.info(f"   Agent log: {AGENT_LOG_FILE}")
    logging.info(f"   API log: {API_LOG_FILE}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module."""
    return logging.getLogger(name)
