"""MK Policy Engine — Declarative safety and governance.

Replaces regex-based command matching with structured, configurable
policies that declare WHAT is allowed, WHEN it needs confirmation,
and HOW to undo it if things go wrong.

Components:
    - PolicyRule: Declarative rules loaded from YAML
    - PolicyEngine: Evaluates actions against rules, returns decisions
    - SnapshotManager: Pre-execution state capture for rollback
    - RollbackHandler: Undo actions using snapshots
    - ChangePreview: Show exactly what will change before executing

Policy example (policies.yaml):
    - name: no-destroy-without-backup
      match:
        tool: zfs
        action: destroy
      require:
        - backup_exists(target)
        - backup_age < 24h
      on_deny: "Cannot destroy: no recent backup exists"

    - name: container-restart-limit
      match:
        tool: docker
        action: restart
      limit:
        count: 3
        period: 1h
        per: container
      on_exceed: "Container restarted 3x in 1h — investigate root cause"
"""

from mk.policy.rules import PolicyRule, PolicyMatch, PolicyAction, PolicyDecision
from mk.policy.engine import PolicyEngine, EvaluationResult
from mk.policy.snapshots import SnapshotManager, Snapshot, SnapshotType
from mk.policy.rollback import RollbackHandler, RollbackPlan, RollbackStep
from mk.policy.preview import ChangePreview, Change, ChangeType

__all__ = [
    "PolicyRule",
    "PolicyMatch",
    "PolicyAction",
    "PolicyDecision",
    "PolicyEngine",
    "EvaluationResult",
    "SnapshotManager",
    "Snapshot",
    "SnapshotType",
    "RollbackHandler",
    "RollbackPlan",
    "RollbackStep",
    "ChangePreview",
    "Change",
    "ChangeType",
]
