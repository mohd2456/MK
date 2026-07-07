"""MK Task Planner — Hierarchical planning with sub-agents.

Replaces the flat ReAct loop with structured task decomposition:

1. User request arrives
2. TaskPlanner decomposes it into a TaskGraph (DAG of sub-tasks)
3. CritiqueGate reviews the plan before execution
4. PlanExecutor walks the DAG, dispatching tasks to specialist SubAgents
5. Results flow back up, with error handling and replanning

Architecture:
    - TaskGraph: DAG of TaskNodes with dependencies and state
    - TaskPlanner: Breaks complex requests into sub-task DAGs
    - SubAgent: Specialist agent with focused tools and system prompt
    - CritiqueGate: Pre-execution safety review of plans
    - PlanExecutor: Orchestrates DAG execution with parallelism
"""

from mk.planner.graph import TaskGraph, TaskNode, TaskStatus, TaskEdge
from mk.planner.planner import TaskPlanner, PlanResult
from mk.planner.sub_agent import SubAgent, AgentCapability, SubAgentRegistry
from mk.planner.critique import CritiqueGate, CritiqueResult, RiskLevel
from mk.planner.executor import PlanExecutor, ExecutionResult

__all__ = [
    "TaskGraph",
    "TaskNode",
    "TaskStatus",
    "TaskEdge",
    "TaskPlanner",
    "PlanResult",
    "SubAgent",
    "AgentCapability",
    "SubAgentRegistry",
    "CritiqueGate",
    "CritiqueResult",
    "RiskLevel",
    "PlanExecutor",
    "ExecutionResult",
]
