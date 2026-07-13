"""MK Core module.

Contains the agent loop, engine, context builder, command router,
and core data models that power the MK operating system.

Engine layering
---------------
There are two engine classes, related by inheritance rather than being
competing implementations:

* :class:`~mk.core.engine.MKEngine` — the base engine. Configuration, LLM
  providers, memory, tools, command routing, and the agent loop. Lightweight;
  safe to construct and use directly with no async startup.
* :class:`~mk.core.engine_v2.MKEngineV2` — the full engine. Subclasses
  ``MKEngine`` and adds the Season 2 subsystems (plugins, task planner,
  proactive ops, semantic memory, policy engine, Tailscale). Those subsystems
  stay dormant until :meth:`MKEngineV2.initialize` is awaited, so an
  un-initialized ``MKEngineV2`` behaves like ``MKEngine``.

Prefer the canonical :data:`Engine` alias (``= MKEngineV2``) or
:func:`create_engine` when constructing an engine, so there is a single
blessed entry point across the CLI, web API, and gateway.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from mk.core.engine import MKEngine
from mk.core.engine_v2 import MKEngineV2

if TYPE_CHECKING:
    from mk.config.settings import Settings

# Canonical engine. Everything that needs "the MK engine" should use this so
# there is one obvious choice. It points at the full Season 2 engine, which is
# a drop-in superset of the base engine.
Engine = MKEngineV2


def create_engine(
    config_path: Optional[str] = None,
    settings: Optional["Settings"] = None,
    **kwargs: Any,
) -> MKEngineV2:
    """Construct the canonical MK engine.

    Returns an :class:`~mk.core.engine_v2.MKEngineV2`. Season 2 subsystems are
    not started here — call ``await engine.initialize()`` when you want plugins,
    ops, semantic memory, and policy enforcement (e.g. in daemon/server mode).

    Args:
        config_path: Path to a config YAML file.
        settings: Pre-built ``Settings`` instance (overrides ``config_path``).
        **kwargs: Forwarded to :class:`MKEngineV2` (feature flags, plugin dirs).

    Returns:
        An un-initialized ``MKEngineV2`` instance.
    """
    return MKEngineV2(config_path=config_path, settings=settings, **kwargs)


__all__: List[str] = ["Engine", "MKEngine", "MKEngineV2", "create_engine"]
