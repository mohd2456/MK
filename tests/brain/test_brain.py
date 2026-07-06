"""Tests for MK's knowledge graph brain."""

import tempfile
from pathlib import Path

import pytest

from mk.brain.graph import KnowledgeGraph
from mk.brain.router import BrainRouter, BrainResponse
from mk.brain.gate import APIGate


@pytest.fixture
def tmp_graph():
    """Create a graph with temp storage."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        graph = KnowledgeGraph(storage_path=f.name)
    return graph


@pytest.fixture
def homelab_graph(tmp_graph):
    """Create a graph pre-loaded with homelab data."""
    graph = tmp_graph

    # Add machines
    graph.add_node("media-server", kind="machine", host="192.168.1.50", role="media")
    graph.add_node("mk-brain", kind="machine", host="192.168.1.10", role="orchestrator")

    # Add services
    graph.add_node("plex", kind="service", port=32400)
    graph.add_node("sonarr", kind="service", port=8989)
    graph.add_node("radarr", kind="service", port=7878)
    graph.add_node("transmission", kind="service", port=9091)

    # Add relationships
    graph.add_edge("plex", "media-server", "runs_on")
    graph.add_edge("sonarr", "media-server", "runs_on")
    graph.add_edge("radarr", "media-server", "runs_on")
    graph.add_edge("transmission", "media-server", "runs_on")

    # Add tools
    graph.add_node("ssh", kind="tool")
    graph.add_node("docker", kind="tool")
    graph.add_node("media", kind="tool")
    graph.add_node("system_monitor", kind="tool")

    # Add a preference
    graph.add_node("movie_genre", kind="preference", value="action")

    return graph


# ─── Graph Tests ──────────────────────────────────────────


class TestKnowledgeGraph:
    def test_add_and_get_node(self, tmp_graph):
        tmp_graph.add_node("plex", kind="service", port=32400)
        node = tmp_graph.get_node("plex")
        assert node is not None
        assert node.kind == "service"
        assert node.data["port"] == 32400

    def test_add_edge(self, tmp_graph):
        tmp_graph.add_node("plex", kind="service")
        tmp_graph.add_node("server", kind="machine")
        tmp_graph.add_edge("plex", "server", "runs_on")

        edges = tmp_graph.get_edges_from("plex")
        assert len(edges) == 1
        assert edges[0].target == "server"
        assert edges[0].relation == "runs_on"

    def test_get_related(self, homelab_graph):
        related = homelab_graph.get_related("media-server")
        assert "plex" in related
        assert "sonarr" in related

    def test_get_related_filtered(self, homelab_graph):
        related = homelab_graph.get_related("plex", relation="runs_on")
        assert "media-server" in related

    def test_find_nodes(self, homelab_graph):
        results = homelab_graph.find_nodes("plex")
        assert len(results) == 1
        assert results[0].id == "plex"

    def test_find_nodes_by_data(self, homelab_graph):
        results = homelab_graph.find_nodes("192.168.1.50")
        assert len(results) == 1
        assert results[0].id == "media-server"

    def test_get_nodes_by_kind(self, homelab_graph):
        services = homelab_graph.get_nodes_by_kind("service")
        assert len(services) == 4

    def test_remove_node(self, homelab_graph):
        homelab_graph.remove_node("plex")
        assert homelab_graph.get_node("plex") is None
        # Edges should be gone too
        edges = homelab_graph.get_edges_from("plex")
        assert len(edges) == 0

    def test_find_path(self, homelab_graph):
        # sonarr → media-server (direct)
        path = homelab_graph.find_path("sonarr", "media-server")
        assert path is not None
        assert path == ["sonarr", "media-server"]

    def test_find_path_multi_hop(self, homelab_graph):
        # plex → sonarr (through media-server)
        path = homelab_graph.find_path("plex", "sonarr")
        assert path is not None
        assert "media-server" in path

    def test_save_and_load(self, tmp_graph):
        tmp_graph.add_node("test", kind="thing", value="hello")
        tmp_graph.add_edge("test", "test", "self")
        tmp_graph.save()

        # Load into new graph
        new_graph = KnowledgeGraph(storage_path=str(tmp_graph._storage_path))
        new_graph.load()

        assert new_graph.get_node("test") is not None
        assert new_graph.get_node("test").data["value"] == "hello"
        assert new_graph.edge_count == 1

    def test_node_count(self, homelab_graph):
        # 2 machines + 4 services + 4 tools + 1 preference = 11
        assert homelab_graph.node_count == 11

    def test_duplicate_edge_updates(self, tmp_graph):
        tmp_graph.add_node("a", kind="x")
        tmp_graph.add_node("b", kind="x")
        tmp_graph.add_edge("a", "b", "likes", score=1)
        tmp_graph.add_edge("a", "b", "likes", score=2)
        assert tmp_graph.edge_count == 1  # Not duplicated
        edges = tmp_graph.get_edges_from("a")
        assert edges[0].data["score"] == 2  # Updated


# ─── Brain Router Tests ───────────────────────────────────


class TestBrainRouter:
    def test_casual_greeting(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("hey")
        assert result.handled is True
        assert "good" in result.response.lower() or "what" in result.response.lower()

    def test_casual_thanks(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("thanks")
        assert result.handled is True
        assert result.response == "Bet."

    def test_restart_known_service(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("restart plex")
        assert result.handled is True
        assert result.tool_call is not None
        assert result.tool_call["tool"] == "docker"
        assert result.tool_call["params"]["action"] == "restart"
        assert result.tool_call["params"]["container"] == "plex"
        assert result.tool_call["params"]["machine"] == "media-server"

    def test_stop_service(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("stop sonarr")
        assert result.handled is True
        assert result.tool_call["tool"] == "docker"
        assert result.tool_call["params"]["action"] == "stop"
        assert result.tool_call["params"]["container"] == "sonarr"

    def test_check_disk(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("disk space")
        assert result.handled is True
        assert result.tool_call["tool"] == "ssh"
        assert "df" in result.tool_call["params"]["command"]

    def test_check_memory(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("ram usage")
        assert result.handled is True
        assert result.tool_call["tool"] == "ssh"
        assert "free" in result.tool_call["params"]["command"]

    def test_list_containers(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("what's running")
        assert result.handled is True
        assert result.tool_call["tool"] == "docker"
        assert result.tool_call["params"]["action"] == "list"

    def test_danger_delete_all(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("delete everything")
        assert result.handled is True
        assert result.needs_confirmation is True
        assert "dangerous" in result.response.lower() or "deletion" in result.risk_message.lower()

    def test_danger_shutdown(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("shutdown the server")
        assert result.handled is True
        assert result.needs_confirmation is True

    def test_danger_rm_rf(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("rm -rf /data")
        assert result.handled is True
        assert result.needs_confirmation is True

    def test_knowledge_where_is(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("where's plex")
        assert result.handled is True
        assert "media-server" in result.response

    def test_complex_goes_to_api(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("help me plan my network with vlans and security zones")
        assert result.handled is False
        assert result.send_to_api is True

    def test_empty_input(self, homelab_graph):
        brain = BrainRouter(homelab_graph)
        result = brain.think("")
        assert result.handled is True
        assert result.response == "What's up?"


# ─── API Gate Tests ───────────────────────────────────────


class TestAPIGate:
    def test_local_handling(self, homelab_graph):
        gate = APIGate(homelab_graph)
        result = gate.process("restart plex")
        assert result.source == "brain"
        assert result.tool_call is not None
        assert result.api_request is None

    def test_api_routing(self, homelab_graph):
        gate = APIGate(homelab_graph)
        result = gate.process("help me design a backup strategy for my homelab")
        assert result.source == "api"
        assert result.api_request is not None
        assert "system_prompt" in result.api_request
        assert "user_message" in result.api_request

    def test_api_context_includes_machines(self, homelab_graph):
        gate = APIGate(homelab_graph)
        result = gate.process("what's the best way to organize my server")
        assert result.source == "api"
        # System prompt should mention machines
        assert "media-server" in result.api_request["system_prompt"]

    def test_teach_and_recall(self, homelab_graph):
        gate = APIGate(homelab_graph)
        gate.teach("favorite_movie", "Dune", kind="preference")

        # Now the graph has it
        node = homelab_graph.get_node("favorite_movie")
        assert node is not None
        assert node.data["value"] == "Dune"

    def test_forget(self, homelab_graph):
        gate = APIGate(homelab_graph)
        gate.teach("temp_fact", "test", kind="fact")
        assert gate.forget("temp_fact") is True
        assert homelab_graph.get_node("temp_fact") is None

    def test_setup_homelab(self, tmp_graph):
        gate = APIGate(tmp_graph)
        gate.setup_homelab({
            "my-server": {
                "host": "10.0.0.1",
                "role": "media",
                "services": ["plex", "sonarr"]
            }
        })

        assert tmp_graph.get_node("my-server") is not None
        assert tmp_graph.get_node("plex") is not None
        related = tmp_graph.get_related("plex", "runs_on")
        assert "my-server" in related

    def test_confirmation_passthrough(self, homelab_graph):
        gate = APIGate(homelab_graph)
        result = gate.process("delete all downloads")
        assert result.source == "brain"
        assert result.needs_confirmation is True
