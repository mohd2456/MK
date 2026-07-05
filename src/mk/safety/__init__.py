"""MK Safety system.

Provides safety mechanisms including:
- Confirmation prompts for dangerous actions
- Audit logging of all actions
- Encrypted secrets management
- Self-health monitoring
"""

from mk.safety.audit import AuditLogger
from mk.safety.confirmation import ConfirmationManager
from mk.safety.health import HealthMonitor
from mk.safety.secrets import SecretsManager

__all__ = [
    "AuditLogger",
    "ConfirmationManager",
    "HealthMonitor",
    "SecretsManager",
]
