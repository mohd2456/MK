"""MK Server Management Module.

TrueNAS-like layer providing home server capabilities managed
entirely through the AI brain. Covers storage, shares, containers,
services, network, monitoring, and backup.

All functions are async and return structured data (dicts/lists).
Each sub-module is independent and can be used standalone.
"""

from __future__ import annotations

__all__ = [
    "storage",
    "shares",
    "containers",
    "services",
    "network",
    "monitor",
    "backup",
]
