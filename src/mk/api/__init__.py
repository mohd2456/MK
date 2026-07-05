"""MK Internal API.

Provides a lightweight HTTP API for communication between
the MK core engine and external gateways (Telegram, etc.).
"""

from mk.api.server import create_app

__all__ = ["create_app"]
