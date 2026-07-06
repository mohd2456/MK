"""Core Knowledge Graph — Nodes, edges, and fact storage.

Simple graph structure where:
- Nodes = things (machines, services, tools, preferences, people)
- Edges = relationships between things
- Facts = queryable knowledge stored in the graph

The graph is persisted to disk as JSON so MK remembers
everything between restarts.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class Node:
    """A single entity in the knowledge graph."""

    def __init__(self, id: str, kind: str, data: Optional[Dict[str, Any]] = None):
        """Create a node.

        Args:
            id: Unique identifier (e.g. "plex", "media-server", "user")
            kind: Node type (e.g. "service", "machine", "person", "tool")
            data: Any extra data attached to this node
        """
        self.id = id
        self.kind = kind
        self.data = data or {}
        self.created_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "data": self.data,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Node":
        node = cls(id=d["id"], kind=d["kind"], data=d.get("data", {}))
        node.created_at = d.get("created_at", time.time())
        return node


class Edge:
    """A relationship between two nodes."""

    def __init__(self, source: str, target: str, relation: str, data: Optional[Dict[str, Any]] = None):
        """Create an edge.

        Args:
            source: Source node ID
            target: Target node ID
            relation: What the relationship is (e.g. "runs_on", "managed_by", "uses")
            data: Extra edge data
        """
        self.source = source
        self.target = target
        self.relation = relation
        self.data = data or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Edge":
        return cls(
            source=d["source"],
            target=d["target"],
            relation=d["relation"],
            data=d.get("data", {}),
        )


class KnowledgeGraph:
    """MK's knowledge graph — stores everything MK knows.

    Simple and fast. Nodes are things, edges connect them.
    Query by node, by kind, by relation, or by keyword in data.
    Persists to a JSON file on disk.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize the graph.

        Args:
            storage_path: Where to save/load the graph. Defaults to ~/.mk/brain.json
        """
        self._nodes: Dict[str, Node] = {}
        self._edges: List[Edge] = []
        self._storage_path = Path(
            storage_path or Path.home() / ".mk" / "brain.json"
        )

    # ─── Add/Remove ───────────────────────────────────────

    def add_node(self, id: str, kind: str, **data) -> Node:
        """Add a node to the graph. Updates if exists.

        Args:
            id: Unique identifier
            kind: Node type
            **data: Any additional data

        Returns:
            The created/updated node
        """
        if id in self._nodes:
            # Update existing
            self._nodes[id].kind = kind
            self._nodes[id].data.update(data)
            return self._nodes[id]

        node = Node(id=id, kind=kind, data=data)
        self._nodes[id] = node
        return node

    def add_edge(self, source: str, target: str, relation: str, **data) -> Edge:
        """Add a relationship between two nodes.

        Args:
            source: Source node ID
            target: Target node ID
            relation: Relationship type
            **data: Extra edge data

        Returns:
            The created edge
        """
        # Don't duplicate edges
        for e in self._edges:
            if e.source == source and e.target == target and e.relation == relation:
                e.data.update(data)
                return e

        edge = Edge(source=source, target=target, relation=relation, data=data)
        self._edges.append(edge)
        return edge

    def remove_node(self, id: str) -> bool:
        """Remove a node and all its edges.

        Args:
            id: Node ID to remove

        Returns:
            True if found and removed
        """
        if id not in self._nodes:
            return False
        del self._nodes[id]
        self._edges = [e for e in self._edges if e.source != id and e.target != id]
        return True

    def remove_edge(self, source: str, target: str, relation: str) -> bool:
        """Remove a specific edge.

        Returns:
            True if found and removed
        """
        before = len(self._edges)
        self._edges = [
            e for e in self._edges
            if not (e.source == source and e.target == target and e.relation == relation)
        ]
        return len(self._edges) < before

    # ─── Query ────────────────────────────────────────────

    def get_node(self, id: str) -> Optional[Node]:
        """Get a node by ID."""
        return self._nodes.get(id)

    def get_nodes_by_kind(self, kind: str) -> List[Node]:
        """Get all nodes of a specific type."""
        return [n for n in self._nodes.values() if n.kind == kind]

    def get_edges_from(self, source: str) -> List[Edge]:
        """Get all edges going out from a node."""
        return [e for e in self._edges if e.source == source]

    def get_edges_to(self, target: str) -> List[Edge]:
        """Get all edges pointing to a node."""
        return [e for e in self._edges if e.target == target]

    def get_related(self, node_id: str, relation: Optional[str] = None) -> List[str]:
        """Get all nodes connected to a given node.

        Args:
            node_id: The node to find connections for
            relation: Optional filter by relation type

        Returns:
            List of connected node IDs
        """
        results: Set[str] = set()
        for e in self._edges:
            if e.source == node_id and (relation is None or e.relation == relation):
                results.add(e.target)
            if e.target == node_id and (relation is None or e.relation == relation):
                results.add(e.source)
        return list(results)

    def find_nodes(self, keyword: str) -> List[Node]:
        """Search for nodes by keyword in ID or data.

        Args:
            keyword: Search term (case-insensitive)

        Returns:
            Matching nodes
        """
        keyword_lower = keyword.lower()
        results = []
        for node in self._nodes.values():
            if keyword_lower in node.id.lower():
                results.append(node)
                continue
            # Check data values
            for v in node.data.values():
                if isinstance(v, str) and keyword_lower in v.lower():
                    results.append(node)
                    break
        return results

    def find_path(self, start: str, end: str, max_hops: int = 5) -> Optional[List[str]]:
        """Find a path between two nodes (BFS).

        Args:
            start: Starting node ID
            end: Target node ID
            max_hops: Maximum path length

        Returns:
            List of node IDs forming the path, or None if no path
        """
        if start not in self._nodes or end not in self._nodes:
            return None

        visited: Set[str] = set()
        queue: List[List[str]] = [[start]]

        while queue:
            path = queue.pop(0)
            current = path[-1]

            if current == end:
                return path

            if current in visited or len(path) > max_hops:
                continue

            visited.add(current)

            for neighbor in self.get_related(current):
                if neighbor not in visited:
                    queue.append(path + [neighbor])

        return None

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    # ─── Persistence ──────────────────────────────────────

    def save(self) -> None:
        """Save the graph to disk."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges],
        }
        self._storage_path.write_text(json.dumps(data, indent=2))

    def load(self) -> bool:
        """Load the graph from disk.

        Returns:
            True if loaded successfully, False if no file exists
        """
        if not self._storage_path.exists():
            return False

        data = json.loads(self._storage_path.read_text())
        self._nodes = {
            n["id"]: Node.from_dict(n) for n in data.get("nodes", [])
        }
        self._edges = [Edge.from_dict(e) for e in data.get("edges", [])]
        return True

    def clear(self) -> None:
        """Clear all nodes and edges."""
        self._nodes.clear()
        self._edges.clear()
