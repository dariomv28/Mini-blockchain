"""Explicit persistence failures, distinct from consensus rejection."""


class StorageError(RuntimeError):
    """A persistence operation failed; the caller must not assume it committed."""


class StorageCorruptionError(StorageError):
    """Stored or supplied data violates the storage format or ledger checks."""


class StorageVersionError(StorageError):
    """The database uses an unsupported schema version."""


class StorageConflictError(StorageError):
    """The database changed since the owning instance loaded its state."""


class StorageClosedError(StorageError):
    """The persistent instance or its connection is no longer usable."""


class StorageCommitUncertainError(StorageError):
    """A commit may have reached disk; reopen before deciding what persisted."""


class StorageConfigurationError(StorageError):
    """The persistence path, runtime or database configuration is unsupported."""
