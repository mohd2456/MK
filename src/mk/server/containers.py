"""Container Manager - Docker lifecycle, compose orchestration, resource management."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult

from ._shell import safe_quote, validate_name
from .models import ComposeStack, ContainerInfo, ContainerState

logger = logging.getLogger(__name__)


class ContainerManager:
    """Manages Docker containers, compose stacks, images, and volumes."""

    def __init__(self, sudo: bool = False, compose_dir: str = "/opt/mk/stacks") -> None:
        self._sudo = sudo
        self._cmd_prefix = "sudo " if sudo else ""
        self._compose_dir = compose_dir

    async def _run(self, cmd: str, check: bool = True) -> Tuple[int, str, str]:
        """Execute a shell command asynchronously."""
        full_cmd = f"{self._cmd_prefix}{cmd}"
        logger.debug(f"Container exec: {full_cmd}")

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        rc = proc.returncode or 0
        out = stdout.decode().strip()
        err = stderr.decode().strip()

        if rc != 0 and check:
            logger.error(f"Command failed ({rc}): {full_cmd}\n{err}")

        return rc, out, err

    async def _run_with_stdin(self, cmd: str, input_data: str) -> Tuple[int, str, str]:
        """Execute a shell command with data passed via stdin."""
        full_cmd = f"{self._cmd_prefix}{cmd}"
        logger.debug(f"Container exec (stdin): {full_cmd}")

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=input_data.encode())
        rc = proc.returncode or 0
        return rc, stdout.decode().strip(), stderr.decode().strip()

    # Container Lifecycle

    async def list_containers(self, all_containers: bool = True) -> ToolResult:
        """List Docker containers with status and resource usage."""
        all_flag = "-a" if all_containers else ""
        fmt = '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}","state":"{{.State}}","status":"{{.Status}}","ports":"{{.Ports}}","size":"{{.Size}}"}'

        rc, out, err = await self._run(f"docker ps {all_flag} --format '{fmt}'")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list containers: {err}")

        containers: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if line.strip():
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return ToolResult(
            success=True,
            output=json.dumps(containers, indent=2),
            metadata={"container_count": len(containers), "containers": containers},
        )

    async def container_stats(self, name: Optional[str] = None) -> ToolResult:
        """Get real-time resource usage stats for containers."""
        target = safe_quote(name) if name else ""
        rc, out, err = await self._run(
            f"docker stats --no-stream --format '{{{{json .}}}}' {target}".strip()
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to get stats: {err}")

        stats: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if line.strip():
                try:
                    stats.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return ToolResult(
            success=True,
            output=json.dumps(stats, indent=2),
            metadata={"stats": stats},
        )

    async def start_container(self, name: str) -> ToolResult:
        """Start a stopped container."""
        validate_name(name, "container name")
        rc, out, err = await self._run(f"docker start {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to start '{name}': {err}")

        return ToolResult(
            success=True,
            output=f"Container '{name}' started",
            side_effects=[f"Container '{name}' is now running"],
            metadata={"container": name, "action": "start"},
        )

    async def stop_container(self, name: str, timeout: int = 10) -> ToolResult:
        """Stop a running container."""
        validate_name(name, "container name")
        rc, out, err = await self._run(f"docker stop -t {int(timeout)} {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to stop '{name}': {err}")

        return ToolResult(
            success=True,
            output=f"Container '{name}' stopped",
            side_effects=[f"Container '{name}' stopped"],
            metadata={"container": name, "action": "stop"},
        )

    async def restart_container(self, name: str, timeout: int = 10) -> ToolResult:
        """Restart a container."""
        validate_name(name, "container name")
        rc, out, err = await self._run(f"docker restart -t {int(timeout)} {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to restart '{name}': {err}")

        return ToolResult(
            success=True,
            output=f"Container '{name}' restarted",
            side_effects=[f"Container '{name}' restarted"],
            metadata={"container": name, "action": "restart"},
        )

    async def remove_container(self, name: str, force: bool = False, volumes: bool = False) -> ToolResult:
        """Remove a container."""
        validate_name(name, "container name")
        flags = ""
        if force:
            flags += "-f "
        if volumes:
            flags += "-v "

        rc, out, err = await self._run(f"docker rm {flags}{safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to remove '{name}': {err}")

        return ToolResult(
            success=True,
            output=f"Container '{name}' removed",
            side_effects=[f"Container '{name}' permanently removed"],
            metadata={"container": name, "action": "remove", "volumes_removed": volumes},
        )

    async def container_logs(
        self, name: str, lines: int = 100, follow: bool = False, since: Optional[str] = None
    ) -> ToolResult:
        """Get container logs."""
        validate_name(name, "container name")
        since_flag = f"--since {safe_quote(since)} " if since else ""
        rc, out, err = await self._run(
            f"docker logs --tail {int(lines)} {since_flag}{safe_quote(name)}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to get logs for '{name}': {err}")

        return ToolResult(
            success=True,
            output=out if out else "(no logs)",
            metadata={"container": name, "lines": lines},
        )

    async def inspect_container(self, name: str) -> ToolResult:
        """Get full container configuration and state."""
        validate_name(name, "container name")
        rc, out, err = await self._run(f"docker inspect {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to inspect '{name}': {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"container": name, "format": "json"},
        )

    # Container Creation

    async def run_container(
        self,
        image: str,
        name: Optional[str] = None,
        ports: Optional[Dict[str, str]] = None,
        volumes: Optional[List[str]] = None,
        environment: Optional[Dict[str, str]] = None,
        restart_policy: str = "unless-stopped",
        network: Optional[str] = None,
        detach: bool = True,
        labels: Optional[Dict[str, str]] = None,
        command: Optional[str] = None,
        memory_limit: Optional[str] = None,
        cpu_limit: Optional[float] = None,
    ) -> ToolResult:
        """Create and start a new container."""
        cmd_parts = ["docker run"]

        if detach:
            cmd_parts.append("-d")
        if name:
            validate_name(name, "container name")
            cmd_parts.append(f"--name {safe_quote(name)}")
        if restart_policy:
            cmd_parts.append(f"--restart {safe_quote(restart_policy)}")
        if network:
            validate_name(network, "network")
            cmd_parts.append(f"--network {safe_quote(network)}")
        if memory_limit:
            cmd_parts.append(f"--memory {safe_quote(memory_limit)}")
        if cpu_limit is not None:
            cmd_parts.append(f"--cpus {float(cpu_limit)}")

        if ports:
            for host_port, container_port in ports.items():
                cmd_parts.append(f"-p {safe_quote(host_port)}:{safe_quote(container_port)}")

        if volumes:
            for vol in volumes:
                cmd_parts.append(f"-v {safe_quote(vol)}")

        if environment:
            for key, value in environment.items():
                cmd_parts.append(f"-e {safe_quote(f'{key}={value}')}")

        if labels:
            for key, value in labels.items():
                cmd_parts.append(f"--label {safe_quote(f'{key}={value}')}")

        cmd_parts.append(safe_quote(image))

        if command:
            cmd_parts.append(safe_quote(command))

        full_cmd = " ".join(cmd_parts)
        rc, out, err = await self._run(full_cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create container: {err}")

        container_id = out[:12] if out else "unknown"
        display_name = name or container_id

        return ToolResult(
            success=True,
            output=f"Container '{display_name}' created and started (ID: {container_id})",
            side_effects=[
                f"Container '{display_name}' running from image '{image}'",
                f"Restart policy: {restart_policy}",
            ],
            metadata={
                "container_id": container_id,
                "name": name,
                "image": image,
                "action": "run",
            },
        )

    # Docker Compose / Stack Management

    async def list_stacks(self) -> ToolResult:
        """List all managed Docker Compose stacks."""
        rc, out, err = await self._run(
            f"find {safe_quote(self._compose_dir)} -name 'docker-compose.yml' -o -name 'compose.yml' 2>/dev/null",
            check=False,
        )

        stacks: List[Dict[str, str]] = []
        if out:
            for compose_file in out.splitlines():
                if compose_file.strip():
                    stack_name = compose_file.split("/")[-2] if "/" in compose_file else "unknown"
                    stacks.append({"name": stack_name, "path": compose_file.strip()})

        return ToolResult(
            success=True,
            output=json.dumps(stacks, indent=2) if stacks else "No stacks found",
            metadata={"stack_count": len(stacks), "stacks": stacks},
        )

    async def deploy_stack(
        self,
        name: str,
        compose_content: str,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> ToolResult:
        """Deploy a Docker Compose stack."""
        validate_name(name, "stack name")
        stack_dir = f"{self._compose_dir}/{name}"

        rc, _, err = await self._run(f"mkdir -p {safe_quote(stack_dir)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create stack dir: {err}")

        compose_path = f"{stack_dir}/docker-compose.yml"
        rc, _, err = await self._run_with_stdin(
            f"tee {safe_quote(compose_path)} > /dev/null", compose_content
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to write compose file: {err}")

        if env_vars:
            env_content = "\n".join(f"{k}={v}" for k, v in env_vars.items())
            env_path = f"{stack_dir}/.env"
            rc, _, err = await self._run_with_stdin(
                f"tee {safe_quote(env_path)} > /dev/null", env_content
            )
            if rc != 0:
                return ToolResult(success=False, error=f"Failed to write .env: {err}")

        rc, out, err = await self._run(
            f"docker compose -f {safe_quote(compose_path)} up -d"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to deploy stack: {err}")

        return ToolResult(
            success=True,
            output=f"Stack '{name}' deployed successfully\n{out}",
            side_effects=[
                f"Stack '{name}' deployed from {compose_path}",
                "Containers created and started",
            ],
            metadata={"stack": name, "path": compose_path, "action": "deploy"},
        )

    async def update_stack(self, name: str) -> ToolResult:
        """Pull latest images and recreate containers for a stack."""
        validate_name(name, "stack name")
        compose_path = f"{self._compose_dir}/{name}/docker-compose.yml"

        rc, out, err = await self._run(f"docker compose -f {safe_quote(compose_path)} pull")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to pull images: {err}")

        rc, out, err = await self._run(
            f"docker compose -f {safe_quote(compose_path)} up -d --force-recreate"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to recreate stack: {err}")

        return ToolResult(
            success=True,
            output=f"Stack '{name}' updated with latest images\n{out}",
            side_effects=[f"Stack '{name}' containers recreated with latest images"],
            metadata={"stack": name, "action": "update"},
        )

    async def destroy_stack(self, name: str, remove_volumes: bool = False) -> ToolResult:
        """Tear down a Docker Compose stack."""
        validate_name(name, "stack name")
        compose_path = f"{self._compose_dir}/{name}/docker-compose.yml"
        vol_flag = "-v" if remove_volumes else ""

        rc, out, err = await self._run(
            f"docker compose -f {safe_quote(compose_path)} down {vol_flag}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to destroy stack: {err}")

        return ToolResult(
            success=True,
            output=f"Stack '{name}' torn down\n{out}",
            side_effects=[
                f"Stack '{name}' containers stopped and removed",
                f"Volumes removed: {remove_volumes}",
            ],
            metadata={"stack": name, "action": "destroy", "volumes_removed": remove_volumes},
        )

    async def stack_logs(self, name: str, lines: int = 100, service: Optional[str] = None) -> ToolResult:
        """Get logs from a compose stack."""
        validate_name(name, "stack name")
        compose_path = f"{self._compose_dir}/{name}/docker-compose.yml"
        service_arg = safe_quote(service) if service else ""

        rc, out, err = await self._run(
            f"docker compose -f {safe_quote(compose_path)} logs --tail {int(lines)} {service_arg}".strip()
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to get stack logs: {err}")

        return ToolResult(
            success=True,
            output=out if out else "(no logs)",
            metadata={"stack": name, "service": service, "lines": lines},
        )

    # Image Management

    async def list_images(self) -> ToolResult:
        """List all Docker images."""
        rc, out, err = await self._run(
            "docker images --format '{{json .}}'"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list images: {err}")

        images: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if line.strip():
                try:
                    images.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return ToolResult(
            success=True,
            output=json.dumps(images, indent=2),
            metadata={"image_count": len(images)},
        )

    async def pull_image(self, image: str) -> ToolResult:
        """Pull a Docker image."""
        rc, out, err = await self._run(f"docker pull {safe_quote(image)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to pull '{image}': {err}")

        return ToolResult(
            success=True,
            output=f"Image '{image}' pulled successfully\n{out}",
            side_effects=[f"Image '{image}' downloaded"],
            metadata={"image": image, "action": "pull"},
        )

    async def prune_images(self, all_unused: bool = False) -> ToolResult:
        """Remove unused Docker images to free disk space."""
        all_flag = "-a " if all_unused else ""
        rc, out, err = await self._run(f"docker image prune {all_flag}-f")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to prune images: {err}")

        return ToolResult(
            success=True,
            output=f"Images pruned:\n{out}",
            side_effects=["Unused Docker images removed"],
            metadata={"all_unused": all_unused, "action": "prune"},
        )

    # Volume Management

    async def list_volumes(self) -> ToolResult:
        """List Docker volumes."""
        rc, out, err = await self._run("docker volume ls --format '{{json .}}'")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list volumes: {err}")

        volumes: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if line.strip():
                try:
                    volumes.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return ToolResult(
            success=True,
            output=json.dumps(volumes, indent=2),
            metadata={"volume_count": len(volumes)},
        )

    async def create_volume(self, name: str, driver: str = "local") -> ToolResult:
        """Create a Docker volume."""
        validate_name(name, "volume name")
        rc, out, err = await self._run(f"docker volume create --driver {safe_quote(driver)} {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create volume: {err}")

        return ToolResult(
            success=True,
            output=f"Volume '{name}' created",
            side_effects=[f"Docker volume '{name}' created"],
            metadata={"volume": name, "driver": driver},
        )

    # Network Management (Docker networks)

    async def list_networks(self) -> ToolResult:
        """List Docker networks."""
        rc, out, err = await self._run("docker network ls --format '{{json .}}'")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list networks: {err}")

        networks: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if line.strip():
                try:
                    networks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return ToolResult(
            success=True,
            output=json.dumps(networks, indent=2),
            metadata={"network_count": len(networks)},
        )

    async def create_network(
        self, name: str, driver: str = "bridge", subnet: Optional[str] = None
    ) -> ToolResult:
        """Create a Docker network."""
        validate_name(name, "network name")
        subnet_flag = f"--subnet {safe_quote(subnet)}" if subnet else ""
        rc, out, err = await self._run(
            f"docker network create --driver {safe_quote(driver)} {subnet_flag} {safe_quote(name)}".strip()
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create network: {err}")

        return ToolResult(
            success=True,
            output=f"Network '{name}' created (driver: {driver})",
            side_effects=[f"Docker network '{name}' created"],
            metadata={"network": name, "driver": driver, "subnet": subnet},
        )

    # System Cleanup

    async def system_prune(self, volumes: bool = False) -> ToolResult:
        """Clean up unused Docker resources."""
        vol_flag = "--volumes " if volumes else ""
        rc, out, err = await self._run(f"docker system prune {vol_flag}-f")
        if rc != 0:
            return ToolResult(success=False, error=f"System prune failed: {err}")

        return ToolResult(
            success=True,
            output=f"Docker system pruned:\n{out}",
            side_effects=["Unused Docker resources cleaned up"],
            metadata={"volumes_pruned": volumes, "action": "system_prune"},
        )

    async def disk_usage(self) -> ToolResult:
        """Show Docker disk usage breakdown."""
        rc, out, err = await self._run("docker system df -v")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to get disk usage: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"action": "disk_usage"},
        )
