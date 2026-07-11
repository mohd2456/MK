"""Encrypted secrets management for MK.

Stores API keys and credentials encrypted at rest using Fernet
symmetric encryption. The encryption key is derived from a
passphrase using PBKDF2.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SecretsError(Exception):
    """Raised when a secrets operation fails."""


class SecretsManager:
    """Encrypted secrets storage using Fernet encryption.

    Secrets are stored as an encrypted JSON file on disk. The encryption
    key is derived from a user-provided passphrase using PBKDF2 with
    a stored salt.

    Attributes:
        secrets_path: Path to the encrypted secrets file.
        salt_path: Path to the salt file used for key derivation.
    """

    def __init__(
        self,
        secrets_dir: Optional[str] = None,
        passphrase: Optional[str] = None,
    ) -> None:
        """Initialize the secrets manager.

        Args:
            secrets_dir: Directory to store encrypted secrets.
                Resolution order:
                    1. Explicit secrets_dir argument
                    2. MK_DATA env var + /secrets
                    3. /var/lib/mk/secrets (deployed install)
                    4. ~/.mk/secrets (development fallback)
            passphrase: Master passphrase for encryption. If None,
                reads from MK_SECRETS_PASSPHRASE environment variable.
        """
        if secrets_dir:
            resolved_dir = secrets_dir
        else:
            mk_data = os.environ.get("MK_DATA")
            if mk_data:
                resolved_dir = os.path.join(mk_data, "secrets")
            elif Path("/var/lib/mk/secrets").exists() or Path("/var/lib/mk").exists():
                resolved_dir = "/var/lib/mk/secrets"
            else:
                resolved_dir = os.path.expanduser("~/.mk/secrets")

        self._secrets_dir = Path(resolved_dir)
        self._secrets_dir.mkdir(parents=True, exist_ok=True)

        self._secrets_path = self._secrets_dir / "vault.enc"
        self._salt_path = self._secrets_dir / "vault.salt"

        passphrase = passphrase or os.environ.get("MK_SECRETS_PASSPHRASE", "")
        if not passphrase:
            raise SecretsError(
                "No passphrase provided. Set MK_SECRETS_PASSPHRASE or pass passphrase parameter."
            )

        self._fernet = self._create_fernet(passphrase)

    def _create_fernet(self, passphrase: str) -> Fernet:
        """Create a Fernet instance from the passphrase and salt.

        If no salt file exists, generates a new random salt.

        Args:
            passphrase: The master passphrase.

        Returns:
            Configured Fernet instance.
        """
        if self._salt_path.exists():
            salt = self._salt_path.read_bytes()
        else:
            salt = os.urandom(16)
            self._salt_path.write_bytes(salt)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
        return Fernet(key)

    def _load_vault(self) -> Dict[str, str]:
        """Load and decrypt the secrets vault.

        Returns:
            Dictionary of secret names to values.
        """
        if not self._secrets_path.exists():
            return {}

        try:
            encrypted_data = self._secrets_path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted_data)
            return json.loads(decrypted.decode("utf-8"))
        except InvalidToken:
            raise SecretsError("Failed to decrypt vault. Wrong passphrase or corrupted file.")

    def _save_vault(self, vault: Dict[str, str]) -> None:
        """Encrypt and save the secrets vault.

        Args:
            vault: Dictionary of secret names to values.
        """
        data = json.dumps(vault).encode("utf-8")
        encrypted = self._fernet.encrypt(data)
        self._secrets_path.write_bytes(encrypted)

    def store_secret(self, name: str, value: str) -> None:
        """Store a secret with the given name.

        If a secret with the same name exists, it is overwritten.

        Args:
            name: The secret identifier.
            value: The secret value to encrypt and store.
        """
        vault = self._load_vault()
        vault[name] = value
        self._save_vault(vault)

    def get_secret(self, name: str) -> Optional[str]:
        """Retrieve a secret by name.

        Args:
            name: The secret identifier.

        Returns:
            The secret value, or None if not found.
        """
        vault = self._load_vault()
        return vault.get(name)

    def delete_secret(self, name: str) -> bool:
        """Delete a secret by name.

        Args:
            name: The secret identifier to delete.

        Returns:
            True if the secret was found and deleted, False otherwise.
        """
        vault = self._load_vault()
        if name in vault:
            del vault[name]
            self._save_vault(vault)
            return True
        return False

    def list_secrets(self) -> List[str]:
        """List all stored secret names (not values).

        Returns:
            List of secret names.
        """
        vault = self._load_vault()
        return list(vault.keys())

    def has_secret(self, name: str) -> bool:
        """Check if a secret exists.

        Args:
            name: The secret identifier to check.

        Returns:
            True if the secret exists.
        """
        vault = self._load_vault()
        return name in vault
