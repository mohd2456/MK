"""Lightweight, dependency-free metrics for MK.

An in-process, Prometheus-compatible counter/histogram collector with no
third-party dependencies. It lives in its own module (rather than inside
``mk.observability``, which imports FastAPI/Starlette) so the core layers —
the LLM router, training capture, etc. — can record metrics without pulling in
web-framework dependencies.

``mk.observability`` re-exports :data:`metrics` and :class:`MetricsCollector`
for backward compatibility, so existing ``from mk.observability import metrics``
imports keep working.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

__all__ = ["MetricsCollector", "metrics"]


class MetricsCollector:
    """Lightweight in-process metrics collector.

    Tracks counters and histograms without external dependencies.
    Exposes metrics in Prometheus text exposition format.
    """

    def __init__(self) -> None:
        self._counters: Dict[str, float] = {}
        self._histograms: Dict[str, list] = {}

    def increment(
        self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name.
            value: Amount to increment (default 1).
            labels: Optional label dict for metric dimensions.
        """
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0.0) + value

    def observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Observe a value for a histogram metric.

        Args:
            name: Metric name.
            value: Observed value.
            labels: Optional label dict.
        """
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        # Keep only last 1000 observations to limit memory
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-500:]

    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Return the current value of a counter (0.0 if unset)."""
        return self._counters.get(self._make_key(name, labels), 0.0)

    def render_prometheus(self) -> str:
        """Render all metrics in Prometheus text exposition format.

        Returns:
            String of metrics in Prometheus format.
        """
        lines: list = []

        # Counters
        for key, value in sorted(self._counters.items()):
            lines.append(f"{key} {value}")

        # Histograms (emit sum and count)
        seen_bases: Set[str] = set()
        for key, values in sorted(self._histograms.items()):
            base_name = key
            if base_name not in seen_bases:
                seen_bases.add(base_name)
                total = sum(values)
                count = len(values)
                lines.append(f"{base_name}_sum {total:.6f}")
                lines.append(f"{base_name}_count {count}")
                if count > 0:
                    lines.append(f"{base_name}_avg {total / count:.6f}")

        return "\n".join(lines) + "\n" if lines else ""

    def _make_key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Create a metric key from name and labels."""
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    # Convenience: which counter names exist (for tests/introspection).
    def counter_names(self) -> List[str]:
        return sorted(self._counters.keys())


# Global metrics instance shared across the process.
metrics = MetricsCollector()
