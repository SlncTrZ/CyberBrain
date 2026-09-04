# SPDX-License-Identifier: MPL-2.0

class CyberBrainError(Exception):
    """Base CyberBrain error."""


class ConfigurationError(CyberBrainError):
    """Invalid or missing runtime configuration."""


class EmbeddingError(CyberBrainError):
    """Embedding generation failed or returned an incompatible vector."""


class StorageError(CyberBrainError):
    """Storage operation failed."""


class ConflictError(CyberBrainError):
    """Entity evolution conflict or concurrent mutation."""


class SensitiveDataError(CyberBrainError):
    """Ingestion rejected because content appears to contain sensitive credentials."""


class ProviderUnavailableError(CyberBrainError):
    """External reasoning/provider transport is unavailable or timed out."""


class ProviderResponseError(CyberBrainError):
    """External provider returned an invalid or explicit error response."""
