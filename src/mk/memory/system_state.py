"""System state memory for homelab tracking.

Tracks the state of homelab machines, their services,
recent actions, and overall system health. Persisted to disk.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mk.memory.models import ServiceInfo, ServiceStatus, SystemState


class SystemStateMemory:
    """System state tracker for homelab machines and services.

    Maintains the current known state of all managed machines,
    their services, and recent actions. Persisted to disk for
    durability across restarts.
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        """Initialize system state memory.

        Args:
            storage_path: Path to storage directory. If None,
                uses ~/.mk/state as default.
        """
        if storage_path:
            self._storage_path = Path(storage_path)
        else:
            self._storage_path = Path.home() / ".mk" / "state"
        self._states: Dict[str, SystemState] = {}

    @property
    def machine_count(self) -> int:
        """Return the number of tracked machines."""
        return len(self._states)

    @property
    def storage_path(self) -> Path:
        """Return the storage path."""
        return self._storage_path

    def update_state(
        self,
        machine: str,
        status: str,
        host: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SystemState:
        """Update the state of a machine.

        Creates the machine entry if it does not exist, or updates
        the existing entry with new status information.

        Args:
            machine: Machine identifier.
            status: New status string (e.g., 'online', 'offline', 'error').
            host: Machine hostname or IP.
            metadata: Additional metadata to store.

        Returns:
            The updated SystemState entry.
        """
        now = datetime.utcnow()

        if machine in self._states:
            state = self._states[machine]
            state.status = status
            state.last_check = now
            if host:
                state.host = host
            if metadata:
                state.metadata.update(metadata)
        else:
            self._states[machine] = SystemState(
                machine_name=machine,
                host=host,
                status=status,
                last_check=now,
                metadata=metadata or {},
            )

        return self._states[machine]

    def update_service(
        self,
        machine: str,
        service_name: str,
        status: ServiceStatus,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update the status of a service on a machine.

        Creates the machine and service entry if they do not exist.

        Args:
            machine: Machine identifier.
            service_name: Name of the service.
            status: Service status.
            metadata: Additional service metadata.
        """
        if machine not in self._states:
            self.update_state(machine, "unknown")

        state = self._states[machine]

        # Find or create the service entry
        for service in state.services:
            if service.name == service_name:
                service.status = status
                service.last_check = datetime.utcnow()
                if metadata:
                    service.metadata.update(metadata)
                return

        # Service not found, create new entry
        state.services.append(
            ServiceInfo(
                name=service_name,
                status=status,
                last_check=datetime.utcnow(),
                metadata=metadata or {},
            )
        )

    def record_action(self, machine: str, action: str) -> None:
        """Record an action taken on a machine.

        Keeps only the most recent 50 actions per machine.

        Args:
            machine: Machine identifier.
            action: Description of the action taken.
        """
        if machine not in self._states:
            self.update_state(machine, "unknown")

        state = self._states[machine]
        timestamp = datetime.utcnow().isoformat()
        state.recent_actions.append(f"[{timestamp}] {action}")

        # Keep only most recent 50 actions
        if len(state.recent_actions) > 50:
            state.recent_actions = state.recent_actions[-50:]

    def get_state(self, machine: str) -> Optional[SystemState]:
        """Get the current state of a machine.

        Args:
            machine: Machine identifier.

        Returns:
            The SystemState entry, or None if not tracked.
        """
        return self._states.get(machine)

    def get_all_states(self) -> List[SystemState]:
        """Get the states of all tracked machines.

        Returns:
            List of all SystemState entries.
        """
        return list(self._states.values())

    def get_machines_by_status(self, status: str) -> List[SystemState]:
        """Get all machines with a given status.

        Args:
            status: The status to filter by.

        Returns:
            List of SystemState entries matching the status.
        """
        return [s for s in self._states.values() if s.status == status]

    def save(self) -> None:
        """Persist all system state to disk.

        Creates the storage directory if it does not exist.
        """
        self._storage_path.mkdir(parents=True, exist_ok=True)
        data_file = self._storage_path / "system_state.json"

        data: Dict[str, Any] = {}
        for name, state in self._states.items():
            entry: Dict[str, Any] = {
                "machine_name": state.machine_name,
                "host": state.host,
                "status": state.status,
                "last_check": state.last_check.isoformat(),
                "recent_actions": state.recent_actions,
                "metadata": state.metadata,
                "services": [],
            }
            for service in state.services:
                entry["services"].append(
                    {
                        "name": service.name,
                        "status": service.status.value,
                        "last_check": service.last_check.isoformat(),
                        "metadata": service.metadata,
                    }
                )
            data[name] = entry

        with open(data_file, "w") as f:
            json.dump(data, f, indent=2)

    def load(self) -> None:
        """Load system state from disk.

        Reads from the JSON persistence file. If the file does not
        exist, starts with empty state.
        """
        data_file = self._storage_path / "system_state.json"
        if not data_file.exists():
            return

        with open(data_file, "r") as f:
            data = json.load(f)

        self._states.clear()
        for name, entry in data.items():
            services = []
            for svc in entry.get("services", []):
                services.append(
                    ServiceInfo(
                        name=svc["name"],
                        status=ServiceStatus(svc["status"]),
                        last_check=datetime.fromisoformat(svc["last_check"]),
                        metadata=svc.get("metadata", {}),
                    )
                )

            self._states[name] = SystemState(
                machine_name=entry["machine_name"],
                host=entry.get("host", ""),
                status=entry["status"],
                last_check=datetime.fromisoformat(entry["last_check"]),
                recent_actions=entry.get("recent_actions", []),
                metadata=entry.get("metadata", {}),
                services=services,
            )
