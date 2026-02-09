"""
Comprehensive Logging Configuration

Sets up structured logging for the entire application with:
- File rotation
- Different log levels
- Structured JSON logging
- Error tracking

IMPORTANT: This module controls ALL log output including what systemd captures.
  - stdout  →  /var/log/smartchatbot_backend.log      (regular log)
  - stderr  →  /var/log/smartchatbot_backend.error.log (error log)

Rules enforced:
  1. Every line must have a timestamp.
  2. Only WARNING+ goes to stderr (error log).
  3. INFO access/heartbeat logs go to rotating files only (not stdout/stderr).
"""

import logging
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


# ---------------------------------------------------------------------------
# CRITICAL: Monkey-patch uvicorn's built-in LOGGING_CONFIG at import time.
#
# Uvicorn's CLI applies its own dictConfig MULTIPLE times during startup,
# which overwrites any handler changes we make in setup_logging().
# By patching the source dict here (at import time), every subsequent
# dictConfig application by uvicorn will use OUR formatters with timestamps.
#
# This is the ONLY reliable way to guarantee timestamps in uvicorn output
# when started via CLI (e.g. systemd calling `uvicorn src.main:app_sio`).
# ---------------------------------------------------------------------------
try:
    import uvicorn.config as _uvi_cfg

    _uvi_cfg.LOGGING_CONFIG["formatters"]["default"]["fmt"] = \
        "%(asctime)s - %(levelprefix)s %(message)s"
    _uvi_cfg.LOGGING_CONFIG["formatters"]["default"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

    _uvi_cfg.LOGGING_CONFIG["formatters"]["access"]["fmt"] = \
        '%(asctime)s - %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'
    _uvi_cfg.LOGGING_CONFIG["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

    # Only WARNING+ from uvicorn.error → stderr  (no INFO lifecycle spam)
    _uvi_cfg.LOGGING_CONFIG["loggers"]["uvicorn.error"]["level"] = "WARNING"
    _uvi_cfg.LOGGING_CONFIG["handlers"]["default"]["level"] = "WARNING"

except (ImportError, KeyError, AttributeError):
    # uvicorn not installed (e.g. in a test runner) — skip gracefully
    pass


# Log directory
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Log files
APP_LOG_FILE = LOG_DIR / "app.log"
ERROR_LOG_FILE = LOG_DIR / "errors.log"
AGENT_LOG_FILE = LOG_DIR / "agents.log"
API_LOG_FILE = LOG_DIR / "api.log"
ACCESS_LOG_FILE = LOG_DIR / "access.log"

# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

_CONSOLE_FMT = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
_CONSOLE_DATEFMT = '%Y-%m-%d %H:%M:%S'


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""

    def format(self, record):
        log_data = {
            "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data

        # Extract request_id from message if present (AgentLogger format)
        msg = record.getMessage()
        if msg.startswith("[req_") or msg.startswith("[http_") or msg.startswith("[ws_"):
            bracket_end = msg.find("]")
            if bracket_end > 0:
                log_data["request_id"] = msg[1:bracket_end]

        return json.dumps(log_data, default=str)


# ---------------------------------------------------------------------------
# Uvicorn log_config override
# ---------------------------------------------------------------------------
# This dict is passed to uvicorn via app startup to replace its default
# formatters.  Every handler now uses a format string that includes a
# timestamp.  "uvicorn.access" is routed to stdout with a timestamp;
# "uvicorn.error" (lifecycle messages) is routed to stderr at WARNING+.

UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": _CONSOLE_FMT,
            "datefmt": _CONSOLE_DATEFMT,
        },
        "access": {
            "format": '%(asctime)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s',
            "datefmt": _CONSOLE_DATEFMT,
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "level": "WARNING",          # Only WARNING+ to stderr
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "level": "INFO",
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["default"],
            "level": "WARNING",          # Only WARNING+ to stderr
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["access"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


# ---------------------------------------------------------------------------
# Application-level logging setup
# ---------------------------------------------------------------------------

def setup_logging():
    """Configure logging for the entire application.

    Call this EARLY (module level in main.py) AND again in the lifespan
    handler so it re-applies after uvicorn reconfigures its loggers.
    """

    # ------------------------------------------------------------------
    # 1.  Root logger
    # ------------------------------------------------------------------
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = []  # Remove any existing handlers

    # Timestamped console formatter (used for stdout AND stderr)
    console_formatter = logging.Formatter(_CONSOLE_FMT, datefmt=_CONSOLE_DATEFMT)

    # stdout handler – INFO+ (systemd captures this as regular log)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(console_formatter)
    # Only emit INFO and WARNING to stdout (not ERROR, which goes to stderr)
    stdout_handler.addFilter(_MaxLevelFilter(logging.WARNING))
    root_logger.addHandler(stdout_handler)

    # stderr handler – ERROR+ only (systemd captures this as error log)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(console_formatter)
    root_logger.addHandler(stderr_handler)

    # ------------------------------------------------------------------
    # 2.  Rotating file handlers (JSON structured)
    # ------------------------------------------------------------------
    app_handler = RotatingFileHandler(APP_LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(app_handler)

    error_handler = RotatingFileHandler(ERROR_LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(error_handler)

    # Agent log file
    agent_logger = logging.getLogger("agent")
    agent_handler = RotatingFileHandler(AGENT_LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
    agent_handler.setLevel(logging.INFO)
    agent_handler.setFormatter(JSONFormatter())
    agent_logger.addHandler(agent_handler)

    # API log file
    api_logger = logging.getLogger("api")
    api_handler = RotatingFileHandler(API_LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
    api_handler.setLevel(logging.INFO)
    api_handler.setFormatter(JSONFormatter())
    api_logger.addHandler(api_handler)

    # ------------------------------------------------------------------
    # 3.  Access / noisy logger file (keeps them out of stdout/stderr)
    # ------------------------------------------------------------------
    access_handler = RotatingFileHandler(ACCESS_LOG_FILE, maxBytes=10*1024*1024, backupCount=3)
    access_handler.setLevel(logging.INFO)
    access_formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt=_CONSOLE_DATEFMT)
    access_handler.setFormatter(access_formatter)

    # ------------------------------------------------------------------
    # 4.  Uvicorn logger overrides
    # ------------------------------------------------------------------
    # uvicorn.access → access.log file + stdout with timestamp
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = []
    uvicorn_access.addHandler(access_handler)   # Rotating file
    uvicorn_access.addHandler(stdout_handler)   # stdout with timestamp
    uvicorn_access.propagate = False

    # uvicorn.error → app.log file + stderr (WARNING+ only with timestamp)
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_error.handlers = []
    uvicorn_error.setLevel(logging.WARNING)     # Block INFO lifecycle msgs from stderr
    uvicorn_error.addHandler(app_handler)       # All levels to app.log
    uvicorn_error.addHandler(stderr_handler)    # ERROR+ to stderr with timestamp
    uvicorn_error.propagate = False

    # uvicorn root logger
    uvicorn_root = logging.getLogger("uvicorn")
    uvicorn_root.handlers = []
    uvicorn_root.addHandler(app_handler)
    uvicorn_root.propagate = False

    # ------------------------------------------------------------------
    # 5.  Noisy third-party loggers → access.log only
    # ------------------------------------------------------------------
    for noisy_name in ["httpx", "httpcore", "urllib3", "engineio",
                       "socketio", "websockets", "engineio.server",
                       "socketio.server"]:
        noisy = logging.getLogger(noisy_name)
        noisy.handlers = []
        noisy.addHandler(access_handler)
        noisy.propagate = False

    logging.info("✅ Logging system initialized")
    logging.info(f"   App log: {APP_LOG_FILE}")
    logging.info(f"   Error log: {ERROR_LOG_FILE}")
    logging.info(f"   Access log: {ACCESS_LOG_FILE}")
    logging.info(f"   Agent log: {AGENT_LOG_FILE}")
    logging.info(f"   API log: {API_LOG_FILE}")


class _MaxLevelFilter(logging.Filter):
    """Only allow records at or below the given level.

    Used to keep ERROR+ off stdout (they go to stderr instead).
    """
    def __init__(self, max_level: int):
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module."""
    return logging.getLogger(name)
