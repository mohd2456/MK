"""User Manager - System users, groups, ACLs, and SSH key management.

The AI-managed identity layer. Replaces manual useradd/usermod and web panels:
- User account creation, modification, deletion
- Group management and membership
- SSH authorized key management
- Password and account locking policies
- ACL management for fine-grained file permissions
- Sudo privilege management

MK manages who has access to what — through conversation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult

from .models import GroupInfo, UserAccount

logger = logging.getLogger(__name__)


class UserManager:
    """Manages system users, groups, SSH keys, and access control.

    Provides a unified interface for all identity and access
    management operations on the server.
    """

    def __init__(self, sudo: bool = True) -> None:
        """Initialize the User Manager.

        Args:
            sudo: Whether to prefix commands with sudo.
        """
        self._sudo = sudo
        self._cmd_prefix = "sudo " if sudo else ""

    async def _run(self, cmd: str, check: bool = True) -> Tuple[int, str, str]:
        """Execute a shell command asynchronously."""
        full_cmd = f"{self._cmd_prefix}{cmd}" if not cmd.startswith("sudo") else cmd
        logger.debug(f"User exec: {full_cmd}")

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


    # ─── User Operations ──────────────────────────────────────────────────

    async def list_users(self, system_users: bool = False) -> ToolResult:
        """List user accounts on the system.

        Args:
            system_users: Include system accounts (UID < 1000).

        Returns:
            ToolResult with user listing.
        """
        if system_users:
            cmd = "getent passwd"
        else:
            cmd = "awk -F: '$3 >= 1000 && $3 < 65534 {print}' /etc/passwd"

        rc, out, err = await self._run(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list users: {err}")

        users: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split(":")
            if len(parts) >= 7:
                users.append({
                    "username": parts[0],
                    "uid": int(parts[2]),
                    "gid": int(parts[3]),
                    "comment": parts[4],
                    "home": parts[5],
                    "shell": parts[6],
                })

        return ToolResult(
            success=True,
            output=json.dumps(users, indent=2),
            metadata={"user_count": len(users), "users": users},
        )

    async def user_info(self, username: str) -> ToolResult:
        """Get detailed information about a user.

        Args:
            username: Username to look up.

        Returns:
            ToolResult with user details.
        """
        rc, out, err = await self._run(f"id {username}")
        if rc != 0:
            return ToolResult(success=False, error=f"User '{username}' not found: {err}")

        # Get groups
        rc2, groups_out, _ = await self._run(f"groups {username}")

        # Get last login
        rc3, login_out, _ = await self._run(f"lastlog -u {username} 2>/dev/null", check=False)

        # Check if locked
        rc4, shadow_out, _ = await self._run(f"passwd -S {username} 2>/dev/null", check=False)
        locked = "L" in shadow_out.split()[1] if shadow_out and len(shadow_out.split()) > 1 else False

        result = {
            "id_info": out,
            "groups": groups_out,
            "last_login": login_out,
            "locked": locked,
        }

        return ToolResult(
            success=True,
            output=json.dumps(result, indent=2),
            metadata={"username": username, "locked": locked},
        )


    async def create_user(
        self,
        username: str,
        home_dir: Optional[str] = None,
        shell: str = "/bin/bash",
        groups: Optional[List[str]] = None,
        system_user: bool = False,
        comment: str = "",
        create_home: bool = True,
    ) -> ToolResult:
        """Create a new user account.

        Args:
            username: Username for the new account.
            home_dir: Home directory path (default: /home/username).
            shell: Login shell.
            groups: Additional groups to add user to.
            system_user: Create as system user (UID < 1000).
            comment: User description/full name.
            create_home: Create home directory.

        Returns:
            ToolResult with creation status.
        """
        cmd_parts = ["useradd"]

        if create_home:
            cmd_parts.append("-m")
        if home_dir:
            cmd_parts.append(f"-d {home_dir}")
        if shell:
            cmd_parts.append(f"-s {shell}")
        if system_user:
            cmd_parts.append("-r")
        if comment:
            cmd_parts.append(f'-c "{comment}"')
        if groups:
            cmd_parts.append(f"-G {','.join(groups)}")

        cmd_parts.append(username)
        cmd = " ".join(cmd_parts)

        rc, out, err = await self._run(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create user: {err}")

        return ToolResult(
            success=True,
            output=f"User '{username}' created",
            side_effects=[
                f"User '{username}' created",
                f"Home directory: {home_dir or f'/home/{username}'}",
            ],
            metadata={"username": username, "action": "create"},
        )

    async def delete_user(self, username: str, remove_home: bool = False) -> ToolResult:
        """Delete a user account.

        Args:
            username: Username to delete.
            remove_home: Also remove home directory and mail spool.

        Returns:
            ToolResult with deletion status.
        """
        r_flag = "-r " if remove_home else ""
        rc, out, err = await self._run(f"userdel {r_flag}{username}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to delete user: {err}")

        return ToolResult(
            success=True,
            output=f"User '{username}' deleted",
            side_effects=[f"User '{username}' removed from system"],
            metadata={"username": username, "home_removed": remove_home},
        )

    async def modify_user(
        self,
        username: str,
        shell: Optional[str] = None,
        groups: Optional[List[str]] = None,
        append_groups: bool = True,
        comment: Optional[str] = None,
        home_dir: Optional[str] = None,
        lock: Optional[bool] = None,
    ) -> ToolResult:
        """Modify an existing user account.

        Args:
            username: Username to modify.
            shell: New login shell.
            groups: Groups to set/add.
            append_groups: Append to existing groups (vs replace).
            comment: New comment/full name.
            home_dir: New home directory.
            lock: Lock (True) or unlock (False) the account.

        Returns:
            ToolResult with modification status.
        """
        changes: List[str] = []

        if shell:
            await self._run(f"usermod -s {shell} {username}")
            changes.append(f"shell={shell}")

        if groups:
            a_flag = "-a " if append_groups else ""
            await self._run(f"usermod {a_flag}-G {','.join(groups)} {username}")
            changes.append(f"groups={'added' if append_groups else 'set'}: {','.join(groups)}")

        if comment is not None:
            await self._run(f'usermod -c "{comment}" {username}')
            changes.append(f"comment={comment}")

        if home_dir:
            await self._run(f"usermod -d {home_dir} -m {username}")
            changes.append(f"home={home_dir}")

        if lock is True:
            await self._run(f"usermod -L {username}")
            changes.append("account locked")
        elif lock is False:
            await self._run(f"usermod -U {username}")
            changes.append("account unlocked")

        if not changes:
            return ToolResult(success=True, output="No changes specified")

        return ToolResult(
            success=True,
            output=f"User '{username}' modified: {', '.join(changes)}",
            side_effects=[f"User '{username}': {c}" for c in changes],
            metadata={"username": username, "changes": changes},
        )


    # ─── Group Operations ─────────────────────────────────────────────────

    async def list_groups(self, system_groups: bool = False) -> ToolResult:
        """List groups on the system.

        Args:
            system_groups: Include system groups (GID < 1000).

        Returns:
            ToolResult with group listing.
        """
        if system_groups:
            cmd = "getent group"
        else:
            cmd = "awk -F: '$3 >= 1000 {print}' /etc/group"

        rc, out, err = await self._run(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list groups: {err}")

        groups: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split(":")
            if len(parts) >= 4:
                members = parts[3].split(",") if parts[3] else []
                groups.append({
                    "name": parts[0],
                    "gid": int(parts[2]),
                    "members": members,
                })

        return ToolResult(
            success=True,
            output=json.dumps(groups, indent=2),
            metadata={"group_count": len(groups), "groups": groups},
        )

    async def create_group(self, name: str, gid: Optional[int] = None) -> ToolResult:
        """Create a new group.

        Args:
            name: Group name.
            gid: Specific GID (auto-assigned if not provided).

        Returns:
            ToolResult with creation status.
        """
        gid_flag = f"-g {gid} " if gid else ""
        rc, out, err = await self._run(f"groupadd {gid_flag}{name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create group: {err}")

        return ToolResult(
            success=True,
            output=f"Group '{name}' created",
            side_effects=[f"Group '{name}' created"],
            metadata={"group": name, "gid": gid},
        )

    async def delete_group(self, name: str) -> ToolResult:
        """Delete a group.

        Args:
            name: Group name to delete.

        Returns:
            ToolResult with deletion status.
        """
        rc, out, err = await self._run(f"groupdel {name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to delete group: {err}")

        return ToolResult(
            success=True,
            output=f"Group '{name}' deleted",
            side_effects=[f"Group '{name}' removed"],
            metadata={"group": name},
        )

    async def add_to_group(self, username: str, group: str) -> ToolResult:
        """Add a user to a group.

        Args:
            username: User to add.
            group: Group to add to.

        Returns:
            ToolResult with status.
        """
        rc, out, err = await self._run(f"usermod -aG {group} {username}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to add to group: {err}")

        return ToolResult(
            success=True,
            output=f"User '{username}' added to group '{group}'",
            side_effects=[f"'{username}' is now a member of '{group}'"],
            metadata={"username": username, "group": group},
        )

    async def remove_from_group(self, username: str, group: str) -> ToolResult:
        """Remove a user from a group.

        Args:
            username: User to remove.
            group: Group to remove from.

        Returns:
            ToolResult with status.
        """
        rc, out, err = await self._run(f"gpasswd -d {username} {group}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to remove from group: {err}")

        return ToolResult(
            success=True,
            output=f"User '{username}' removed from group '{group}'",
            side_effects=[f"'{username}' removed from '{group}'"],
            metadata={"username": username, "group": group},
        )


    # ─── SSH Key Management ───────────────────────────────────────────────

    async def list_ssh_keys(self, username: str) -> ToolResult:
        """List SSH authorized keys for a user.

        Args:
            username: Username to list keys for.

        Returns:
            ToolResult with key listing.
        """
        # Get home directory
        rc, home, err = await self._run(
            f"getent passwd {username} | cut -d: -f6"
        )
        if rc != 0 or not home:
            return ToolResult(success=False, error=f"User '{username}' not found")

        auth_keys_path = f"{home}/.ssh/authorized_keys"
        rc, out, err = await self._run(f"cat {auth_keys_path} 2>/dev/null", check=False)

        keys: List[Dict[str, str]] = []
        if rc == 0 and out:
            for i, line in enumerate(out.splitlines()):
                if line.strip() and not line.startswith("#"):
                    parts = line.split()
                    key_type = parts[0] if parts else "unknown"
                    comment = parts[-1] if len(parts) >= 3 else ""
                    keys.append({
                        "index": i,
                        "type": key_type,
                        "comment": comment,
                        "key_preview": line[:80] + "..." if len(line) > 80 else line,
                    })

        return ToolResult(
            success=True,
            output=json.dumps(keys, indent=2) if keys else "No SSH keys configured",
            metadata={"username": username, "key_count": len(keys)},
        )

    async def add_ssh_key(self, username: str, public_key: str) -> ToolResult:
        """Add an SSH public key to a user's authorized_keys.

        Args:
            username: Username to add key for.
            public_key: Full SSH public key string.

        Returns:
            ToolResult with key addition status.
        """
        # Get home directory
        rc, home, _ = await self._run(f"getent passwd {username} | cut -d: -f6")
        if rc != 0 or not home:
            return ToolResult(success=False, error=f"User '{username}' not found")

        ssh_dir = f"{home}/.ssh"
        auth_keys = f"{ssh_dir}/authorized_keys"

        # Ensure .ssh directory exists with correct permissions
        await self._run(f"mkdir -p {ssh_dir}")
        await self._run(f"chmod 700 {ssh_dir}")
        await self._run(f"chown {username}:{username} {ssh_dir}")

        # Append key
        rc, _, err = await self._run(
            f"bash -c 'echo \"{public_key}\" >> {auth_keys}'"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to add SSH key: {err}")

        # Fix permissions
        await self._run(f"chmod 600 {auth_keys}")
        await self._run(f"chown {username}:{username} {auth_keys}")

        # Extract comment from key for display
        key_parts = public_key.split()
        comment = key_parts[-1] if len(key_parts) >= 3 else "unnamed"

        return ToolResult(
            success=True,
            output=f"SSH key '{comment}' added for user '{username}'",
            side_effects=[f"SSH key added to {auth_keys}"],
            metadata={"username": username, "key_comment": comment},
        )

    async def remove_ssh_key(self, username: str, key_index: int) -> ToolResult:
        """Remove an SSH key by index from a user's authorized_keys.

        Args:
            username: Username.
            key_index: Line index (0-based) of the key to remove.

        Returns:
            ToolResult with removal status.
        """
        rc, home, _ = await self._run(f"getent passwd {username} | cut -d: -f6")
        if rc != 0 or not home:
            return ToolResult(success=False, error=f"User '{username}' not found")

        auth_keys = f"{home}/.ssh/authorized_keys"
        # sed line numbers are 1-based
        line_num = key_index + 1
        rc, _, err = await self._run(f"sed -i '{line_num}d' {auth_keys}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to remove key: {err}")

        return ToolResult(
            success=True,
            output=f"SSH key at index {key_index} removed for '{username}'",
            side_effects=[f"Key removed from {auth_keys}"],
            metadata={"username": username, "key_index": key_index},
        )

    async def generate_ssh_keypair(
        self, username: str, key_type: str = "ed25519", comment: Optional[str] = None
    ) -> ToolResult:
        """Generate a new SSH keypair for a user.

        Args:
            username: User to generate key for.
            key_type: Key type (ed25519, rsa).
            comment: Key comment.

        Returns:
            ToolResult with the public key.
        """
        rc, home, _ = await self._run(f"getent passwd {username} | cut -d: -f6")
        if rc != 0 or not home:
            return ToolResult(success=False, error=f"User '{username}' not found")

        key_comment = comment or f"{username}@mk"
        key_path = f"{home}/.ssh/id_{key_type}"

        rc, out, err = await self._run(
            f'ssh-keygen -t {key_type} -C "{key_comment}" -f {key_path} -N ""'
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Key generation failed: {err}")

        # Read public key
        rc, pubkey, _ = await self._run(f"cat {key_path}.pub")

        # Fix ownership
        await self._run(f"chown {username}:{username} {key_path} {key_path}.pub")

        return ToolResult(
            success=True,
            output=f"SSH keypair generated for '{username}'\nPublic key:\n{pubkey}",
            side_effects=[f"Keypair created at {key_path}"],
            metadata={"username": username, "public_key": pubkey, "key_path": key_path},
        )


    # ─── Sudo / Privilege Management ──────────────────────────────────────

    async def grant_sudo(self, username: str, passwordless: bool = False) -> ToolResult:
        """Grant sudo privileges to a user.

        Args:
            username: User to grant sudo.
            passwordless: Allow sudo without password.

        Returns:
            ToolResult with status.
        """
        if passwordless:
            rule = f"{username} ALL=(ALL) NOPASSWD: ALL"
        else:
            rule = f"{username} ALL=(ALL) ALL"

        sudoers_file = f"/etc/sudoers.d/{username}"
        rc, _, err = await self._run(
            f"bash -c 'echo \"{rule}\" > {sudoers_file}'"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to grant sudo: {err}")

        await self._run(f"chmod 440 {sudoers_file}")

        # Validate sudoers syntax
        rc, _, err = await self._run(f"visudo -c -f {sudoers_file}")
        if rc != 0:
            # Rollback invalid sudoers
            await self._run(f"rm -f {sudoers_file}")
            return ToolResult(success=False, error=f"Invalid sudoers syntax: {err}")

        return ToolResult(
            success=True,
            output=f"Sudo {'(passwordless)' if passwordless else ''} granted to '{username}'",
            side_effects=[f"Sudoers file created: {sudoers_file}"],
            metadata={"username": username, "passwordless": passwordless},
        )

    async def revoke_sudo(self, username: str) -> ToolResult:
        """Revoke sudo privileges from a user.

        Args:
            username: User to revoke sudo from.

        Returns:
            ToolResult with status.
        """
        sudoers_file = f"/etc/sudoers.d/{username}"
        rc, _, err = await self._run(f"rm -f {sudoers_file}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to revoke sudo: {err}")

        # Also remove from sudo/wheel group
        await self._run(f"gpasswd -d {username} sudo 2>/dev/null", check=False)
        await self._run(f"gpasswd -d {username} wheel 2>/dev/null", check=False)

        return ToolResult(
            success=True,
            output=f"Sudo revoked from '{username}'",
            side_effects=[f"Sudoers file removed, user removed from sudo/wheel groups"],
            metadata={"username": username},
        )

    # ─── ACL Management ───────────────────────────────────────────────────

    async def get_acl(self, path: str) -> ToolResult:
        """Get ACL (Access Control List) for a file/directory.

        Args:
            path: Filesystem path.

        Returns:
            ToolResult with ACL information.
        """
        rc, out, err = await self._run(f"getfacl {path}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to get ACL: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"path": path, "format": "posix_acl"},
        )

    async def set_acl(
        self,
        path: str,
        user: Optional[str] = None,
        group: Optional[str] = None,
        permissions: str = "rwx",
        recursive: bool = False,
        default: bool = False,
    ) -> ToolResult:
        """Set ACL permissions on a file/directory.

        Args:
            path: Filesystem path.
            user: User to set permissions for.
            group: Group to set permissions for.
            permissions: Permission string (rwx, rx, r, etc.).
            recursive: Apply recursively.
            default: Set as default ACL (for directories).

        Returns:
            ToolResult with ACL set status.
        """
        if not user and not group:
            return ToolResult(success=False, error="Either user or group must be specified")

        r_flag = "-R " if recursive else ""
        d_prefix = "d:" if default else ""

        if user:
            acl_spec = f"{d_prefix}u:{user}:{permissions}"
        else:
            acl_spec = f"{d_prefix}g:{group}:{permissions}"

        rc, out, err = await self._run(f"setfacl {r_flag}-m {acl_spec} {path}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set ACL: {err}")

        return ToolResult(
            success=True,
            output=f"ACL set: {acl_spec} on {path}",
            side_effects=[f"ACL '{acl_spec}' applied to {path}"],
            metadata={"path": path, "acl": acl_spec, "recursive": recursive},
        )

    async def remove_acl(self, path: str, user: Optional[str] = None, group: Optional[str] = None) -> ToolResult:
        """Remove ACL entries for a user or group.

        Args:
            path: Filesystem path.
            user: User to remove ACL for.
            group: Group to remove ACL for.

        Returns:
            ToolResult with removal status.
        """
        if user:
            acl_spec = f"u:{user}"
        elif group:
            acl_spec = f"g:{group}"
        else:
            return ToolResult(success=False, error="User or group required")

        rc, out, err = await self._run(f"setfacl -x {acl_spec} {path}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to remove ACL: {err}")

        return ToolResult(
            success=True,
            output=f"ACL removed: {acl_spec} from {path}",
            side_effects=[f"ACL '{acl_spec}' removed from {path}"],
            metadata={"path": path, "removed_acl": acl_spec},
        )

    # ─── Password Management ─────────────────────────────────────────────

    async def set_password(self, username: str, password: str) -> ToolResult:
        """Set a user's password.

        Args:
            username: User to set password for.
            password: New password.

        Returns:
            ToolResult with status.
        """
        rc, _, err = await self._run(
            f"bash -c 'echo \"{username}:{password}\" | chpasswd'"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set password: {err}")

        return ToolResult(
            success=True,
            output=f"Password set for '{username}'",
            side_effects=[f"Password changed for '{username}'"],
            metadata={"username": username},
        )

    async def lock_account(self, username: str) -> ToolResult:
        """Lock a user account (prevent login).

        Args:
            username: User to lock.

        Returns:
            ToolResult with status.
        """
        rc, _, err = await self._run(f"usermod -L {username}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to lock account: {err}")

        return ToolResult(
            success=True,
            output=f"Account '{username}' locked",
            side_effects=[f"User '{username}' can no longer log in"],
            metadata={"username": username, "locked": True},
        )

    async def unlock_account(self, username: str) -> ToolResult:
        """Unlock a user account.

        Args:
            username: User to unlock.

        Returns:
            ToolResult with status.
        """
        rc, _, err = await self._run(f"usermod -U {username}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to unlock account: {err}")

        return ToolResult(
            success=True,
            output=f"Account '{username}' unlocked",
            side_effects=[f"User '{username}' can now log in"],
            metadata={"username": username, "locked": False},
        )
