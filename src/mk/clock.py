"""Time helpers for MK.

Provides a non-deprecated replacement for :func:`datetime.datetime.utcnow`.

``datetime.utcnow()`` was deprecated in Python 3.12 and is scheduled for
removal. However, it returns a *naive* datetime (no ``tzinfo``), and MK relies
on that behavior throughout: timestamps are serialized with ``.isoformat()``
without a UTC offset, and datetimes are compared to one another without
timezone awareness. Swapping in ``datetime.now(UTC)`` directly would change
serialization output (adding ``+00:00``) and could raise ``TypeError`` when an
aware value is compared to a stored naive one.

:func:`utcnow` preserves the exact historical semantics (naive UTC) while using
a timezone-aware call under the hood, so it will not break on future Python
versions and emits no deprecation warning.
"""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["utcnow"]


def utcnow() -> datetime:
    """Return the current UTC time as a naive :class:`datetime.datetime`.

    Behaviorally equivalent to the deprecated ``datetime.utcnow()``: the
    returned value has no ``tzinfo`` and represents the current time in UTC.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
