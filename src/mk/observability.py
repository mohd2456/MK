"""Observability module for MK.

Provides structured JSON logging, request timing, and a lightweight
Prometheus-compatible metrics endpoint. Designed for homelab use
with minimal overhead and no external dependencies beyond stdlib.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from functools import wraps
from typing import Any, Callable, Dict, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging.

    Outputs one JSON object per log line, suitable for ingestion
    by log aggregators or simple grep-based filtering.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request_id if present
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id

        # Add extra fields
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include any extra attributes added to the log record
        for key in ("duration_ms", "method", "path", "status_code", "client_ip"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, default=str)


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
) -> None:
    """Configure structured logging for MK.

    Sets up the root logger with a JSON formatter (or standard formatter
    for development). Should be called early in application startup.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
        json_format: If True, use JSON formatter. If False, use standard format.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------
# Metrics Collector (Prometheus-compatible, in-process)
# ---------------------------------------------------------------
#
# The collector implementation lives in the dependency-free ``mk.metrics``
# module so core layers can record metrics without importing FastAPI/Starlette.
# Re-exported here for backward compatibility.
from mk.metrics import MetricsCollector, metrics  # noqa: E402,F401


# ---------------------------------------------------------------
# FastAPI Middleware
# ---------------------------------------------------------------


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that adds a unique request_id to each request.

    The request_id is attached to the request state and included
    in log records for correlation.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        # Track timing
        start = time.time()

        response = await call_next(request)

        duration = time.time() - start
        duration_ms = duration * 1000

        # Record metrics
        metrics.increment(
            "mk_requests_total",
            labels={"method": request.method, "path": request.url.path},
        )
        metrics.observe(
            "mk_response_time_seconds",
            duration,
            labels={"method": request.method},
        )

        if response.status_code >= 400:
            metrics.increment(
                "mk_errors_total",
                labels={"status": str(response.status_code)},
            )

        # Add request_id to response headers
        response.headers["X-Request-ID"] = request_id

        # Log the request
        logger = logging.getLogger("mk.http")
        logger.info(
            "HTTP %s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": str(request.url.path),
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 1),
                "client_ip": request.client.host if request.client else "unknown",
            },
        )

        return response


# ---------------------------------------------------------------
# Timing Decorator
# ---------------------------------------------------------------


def timed(name: Optional[str] = None):
    """Decorator to time async function execution and record metrics.

    Usage:
        @timed("llm_inference")
        async def call_llm(...):
            ...

    Args:
        name: Metric name. Defaults to the function name.
    """

    def decorator(func: Callable) -> Callable:
        metric_name = name or f"mk_{func.__name__}_seconds"

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                metrics.observe(metric_name, duration)

        return wrapper

    return decorator
