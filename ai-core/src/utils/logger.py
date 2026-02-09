"""Logging utility for agent actions."""
import logging
import time
import traceback
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger("agent")

class AgentLogger:
    """Enhanced logger for tracking agent actions, tool calls, timing, and failures."""
    
    def __init__(self, request_id: Optional[str] = None):
        self.logs: List[Dict[str, Any]] = []
        self.request_id = request_id or f"req_{int(time.time() * 1000)}"
        self._start_time = time.monotonic()
        self._step_counter = 0
        self._timers: Dict[str, float] = {}
    
    def _elapsed_ms(self) -> int:
        """Milliseconds since logger was created."""
        return int((time.monotonic() - self._start_time) * 1000)
    
    def _next_step(self) -> int:
        self._step_counter += 1
        return self._step_counter
    
    def log(self, message: str, metadata: Dict[str, Any] = None):
        """Log a message with timestamp, step number, and optional metadata."""
        now = datetime.now(timezone.utc)
        step = self._next_step()
        elapsed = self._elapsed_ms()
        
        log_entry = {
            "step": step,
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "elapsed_ms": elapsed,
            "request_id": self.request_id,
            "message": message,
            "metadata": metadata or {}
        }
        self.logs.append(log_entry)
        
        # Structured console output: [step] +elapsed_ms | message | metadata
        console_msg = f"[{self.request_id}] #{step:03d} +{elapsed}ms | {message}"
        if metadata:
            # Compact metadata for console
            meta_str = " | ".join(f"{k}={v}" for k, v in metadata.items())
            console_msg += f" | {meta_str}"
        logger.info(console_msg)
    
    def log_action(self, action: str, component: str, detail: str = "",
                   metadata: Dict[str, Any] = None):
        """Log a specific action with component identification."""
        msg = f"[{component}] {action}"
        if detail:
            msg += f": {detail}"
        combined_meta = {"component": component, "action": action}
        if metadata:
            combined_meta.update(metadata)
        self.log(msg, combined_meta)
    
    def log_api_call(self, service: str, endpoint: str, method: str = "GET",
                     params: Dict[str, Any] = None, status: str = "started"):
        """Log an external API call with service, endpoint, and parameters."""
        meta = {
            "service": service,
            "endpoint": endpoint,
            "method": method,
            "status": status
        }
        if params:
            meta["params"] = params
        self.log(f"🌐 [{service}] {method} {endpoint} → {status}", meta)
    
    def log_error(self, component: str, error: Exception, context: str = ""):
        """Log an error with full traceback and context."""
        error_type = type(error).__name__
        error_msg = str(error)
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        tb_str = "".join(tb[-3:])  # Last 3 frames for brevity
        
        meta = {
            "component": component,
            "error_type": error_type,
            "error_message": error_msg,
            "traceback": tb_str,
            "context": context
        }
        self.log(f"❌ [{component}] {error_type}: {error_msg}", meta)
        # Also log to Python error logger for errors.log capture
        logging.error(
            f"[{self.request_id}] [{component}] {error_type}: {error_msg} | context={context}",
            exc_info=False
        )
    
    def log_route_decision(self, path: str, agent: str, confidence: float,
                           reason: str, category: str = ""):
        """Log a routing decision with all critical fields."""
        meta = {
            "path": path,
            "agent": agent,
            "confidence": confidence,
            "reason": reason,
            "category": category
        }
        self.log(
            f"🛤️ [ROUTE] path={path} | agent={agent} | "
            f"confidence={confidence:.3f} | category={category} | reason={reason}",
            meta
        )
    
    def start_timer(self, label: str):
        """Start a named timer for measuring duration."""
        self._timers[label] = time.monotonic()
    
    def stop_timer(self, label: str) -> int:
        """Stop a named timer and return elapsed milliseconds."""
        start = self._timers.pop(label, None)
        if start is None:
            return 0
        elapsed = int((time.monotonic() - start) * 1000)
        self.log(f"⏱️ [{label}] completed in {elapsed}ms", {"timer": label, "duration_ms": elapsed})
        return elapsed
    
    def get_logs(self) -> list:
        """Get all logged entries."""
        return self.logs
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the request lifecycle."""
        total_ms = self._elapsed_ms()
        error_count = sum(1 for l in self.logs if "error_type" in l.get("metadata", {}))
        return {
            "request_id": self.request_id,
            "total_steps": self._step_counter,
            "total_duration_ms": total_ms,
            "error_count": error_count,
            "start_time": self.logs[0]["timestamp"] if self.logs else None,
            "end_time": self.logs[-1]["timestamp"] if self.logs else None,
        }
    
    def clear(self):
        """Clear all logs."""
        self.logs = []
        self._step_counter = 0
        self._timers = {}
