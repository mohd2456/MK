"""Plugin authoring decorators.

Provides the @plugin_tool decorator for clean, minimal plugin code.
Plugin authors don't need to know about manifests or sandboxes —
they just write async functions with this decorator and a plugin.yaml.

Example usage in a plugin's tools.py:

    from mk.plugins.decorators import plugin_tool

    @plugin_tool(
        description="Search for a movie in Radarr",
        dangerous=False,
    )
    async def search_movie(query: str, year: int = 0) -> str:
        # Implementation here
        return f"Found results for: {query}"

The decorator is optional — the loader also matches by function name.
But it adds metadata that improves documentation and validation.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Dict, Optional


def plugin_tool(
    description: str = "",
    dangerous: bool = False,
    confirm_message: Optional[str] = None,
) -> Callable:
    """Decorator marking a function as a plugin tool.

    Attaches metadata to the function that the PluginLoader uses
    for validation and documentation generation.

    Args:
        description: Human-readable description for LLM prompts.
        dangerous: Whether this tool performs destructive actions.
        confirm_message: Custom confirmation prompt if dangerous.

    Returns:
        Decorator function.

    Example:
        @plugin_tool(description="Restart a container")
        async def restart(container_name: str) -> str:
            ...
    """

    def decorator(func: Callable) -> Callable:
        # Attach metadata to the function
        func._is_plugin_tool = True  # type: ignore[attr-defined]
        func._tool_description = description  # type: ignore[attr-defined]
        func._tool_dangerous = dangerous  # type: ignore[attr-defined]
        func._tool_confirm_message = confirm_message  # type: ignore[attr-defined]

        @functools.wraps(func)
        async def wrapper(**kwargs: Any) -> Any:
            # If the function is not async, run it in an executor
            if inspect.iscoroutinefunction(func):
                return await func(**kwargs)
            else:
                import asyncio

                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: func(**kwargs))

        # Copy metadata to wrapper
        wrapper._is_plugin_tool = True  # type: ignore[attr-defined]
        wrapper._tool_description = description  # type: ignore[attr-defined]
        wrapper._tool_dangerous = dangerous  # type: ignore[attr-defined]
        wrapper._tool_confirm_message = confirm_message  # type: ignore[attr-defined]

        return wrapper

    return decorator


def extract_schema_from_function(func: Callable) -> Dict[str, Any]:
    """Extract a JSON Schema from a function's type hints.

    Inspects the function signature and builds a parameters schema
    from its type annotations. Used when a plugin.yaml doesn't
    explicitly define parameter schemas.

    Args:
        func: The function to inspect.

    Returns:
        JSON Schema dict describing the function's parameters.

    Example:
        async def search(query: str, limit: int = 10) -> str:
            ...

        schema = extract_schema_from_function(search)
        # Returns:
        # {
        #     "type": "object",
        #     "properties": {
        #         "query": {"type": "string"},
        #         "limit": {"type": "integer", "default": 10}
        #     },
        #     "required": ["query"]
        # }
    """
    sig = inspect.signature(func)
    properties: Dict[str, Any] = {}
    required: list = []

    # Python type -> JSON Schema type mapping
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    for param_name, param in sig.parameters.items():
        # Skip **kwargs and *args
        if param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue

        # Skip 'self' and 'cls'
        if param_name in ("self", "cls"):
            continue

        # Determine type
        annotation = param.annotation
        if annotation == inspect.Parameter.empty:
            json_type = "string"  # Default to string
        elif annotation in type_map:
            json_type = type_map[annotation]
        else:
            json_type = "string"

        prop: Dict[str, Any] = {"type": json_type}

        # Check for default value
        if param.default != inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(param_name)

        properties[param_name] = prop

    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema
