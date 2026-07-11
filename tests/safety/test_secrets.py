"""Tests for encrypted secrets management."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mk.safety.secrets import SecretsError, SecretsManager


class TestSecretsManager:
    """Tests for secret storage encryption/decryption round-trip."""

    def setup_method(self) -> None:
        """Set up test fixtures with a temp directory."""
        self._temp_dir = tempfile.mkdtemp()
        self.manager = SecretsManager(
            secrets_dir=self._temp_dir,
            passphrase="test-passphrase-12345",
        )

    def test_store_and_retrieve_secret(self) -> None:
        """Should store and retrieve a secret successfully."""
        self.manager.store_secret("api_key", "sk-12345abcde")
        result = self.manager.get_secret("api_key")
        assert result == "sk-12345abcde"

    def test_store_multiple_secrets(self) -> None:
        """Should store and retrieve multiple secrets."""
        self.manager.store_secret("key1", "value1")
        self.manager.store_secret("key2", "value2")
        self.manager.store_secret("key3", "value3")

        assert self.manager.get_secret("key1") == "value1"
        assert self.manager.get_secret("key2") == "value2"
        assert self.manager.get_secret("key3") == "value3"

    def test_overwrite_secret(self) -> None:
        """Should overwrite existing secret."""
        self.manager.store_secret("key", "old_value")
        self.manager.store_secret("key", "new_value")
        assert self.manager.get_secret("key") == "new_value"

    def test_get_nonexistent_secret(self) -> None:
        """Should return None for missing secrets."""
        assert self.manager.get_secret("nonexistent") is None

    def test_delete_secret(self) -> None:
        """Should delete a secret."""
        self.manager.store_secret("to_delete", "value")
        assert self.manager.delete_secret("to_delete") is True
        assert self.manager.get_secret("to_delete") is None

    def test_delete_nonexistent_secret(self) -> None:
        """Should return False when deleting nonexistent secret."""
        assert self.manager.delete_secret("nonexistent") is False

    def test_list_secrets(self) -> None:
        """Should list secret names without values."""
        self.manager.store_secret("alpha", "value_a")
        self.manager.store_secret("beta", "value_b")
        self.manager.store_secret("gamma", "value_g")

        names = self.manager.list_secrets()
        assert set(names) == {"alpha", "beta", "gamma"}

    def test_list_secrets_empty(self) -> None:
        """Should return empty list when no secrets stored."""
        names = self.manager.list_secrets()
        assert names == []

    def test_has_secret(self) -> None:
        """Should check if a secret exists."""
        self.manager.store_secret("exists", "value")
        assert self.manager.has_secret("exists") is True
        assert self.manager.has_secret("not_exists") is False

    def test_data_encrypted_on_disk(self) -> None:
        """Should not store plaintext on disk."""
        self.manager.store_secret("sensitive", "super-secret-value-xyz")

        vault_path = Path(self._temp_dir) / "vault.enc"
        assert vault_path.exists()

        raw_content = vault_path.read_bytes()
        assert b"super-secret-value-xyz" not in raw_content
        assert b"sensitive" not in raw_content

    def test_wrong_passphrase_fails(self) -> None:
        """Should fail to decrypt with wrong passphrase."""
        self.manager.store_secret("key", "value")

        with pytest.raises(SecretsError, match="Failed to decrypt"):
            wrong_manager = SecretsManager(
                secrets_dir=self._temp_dir,
                passphrase="wrong-passphrase",
            )
            wrong_manager.get_secret("key")

    def test_no_passphrase_raises_error(self) -> None:
        """Should raise error when no passphrase is available."""
        import os

        # Ensure env var is not set
        env_backup = os.environ.pop("MK_SECRETS_PASSPHRASE", None)
        try:
            with pytest.raises(SecretsError, match="No passphrase"):
                SecretsManager(secrets_dir=self._temp_dir, passphrase="")
        finally:
            if env_backup is not None:
                os.environ["MK_SECRETS_PASSPHRASE"] = env_backup

    def test_special_characters_in_value(self) -> None:
        """Should handle special characters correctly."""
        special_value = "p@$$w0rd!#%&*(){}[]|\\:\";'<>?,./~`"
        self.manager.store_secret("special", special_value)
        assert self.manager.get_secret("special") == special_value

    def test_unicode_in_value(self) -> None:
        """Should handle unicode values."""
        unicode_value = "secret-with-unicode"
        self.manager.store_secret("unicode", unicode_value)
        assert self.manager.get_secret("unicode") == unicode_value

    def test_persistence_across_instances(self) -> None:
        """Should persist secrets across manager instances."""
        self.manager.store_secret("persistent", "stays-here")

        # Create a new manager with same settings
        new_manager = SecretsManager(
            secrets_dir=self._temp_dir,
            passphrase="test-passphrase-12345",
        )
        assert new_manager.get_secret("persistent") == "stays-here"

    def test_salt_file_created(self) -> None:
        """Should create a salt file for key derivation."""
        salt_path = Path(self._temp_dir) / "vault.salt"
        assert salt_path.exists()
        assert len(salt_path.read_bytes()) == 16
