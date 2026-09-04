# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cyberbrain.core.errors import (
    ConfigurationError,
    ConflictError,
    EmbeddingError,
    ProviderResponseError,
    ProviderUnavailableError,
    SensitiveDataError,
    StorageError,
)


class ErrorType(StrEnum):
    AUTHENTICATION = "authentication_error"
    VALIDATION = "validation_error"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    SENSITIVE_DATA = "sensitive_data"
    CONFIGURATION = "configuration_error"
    UNAVAILABLE = "unavailable"
    INTERNAL = "internal_error"


@dataclass(frozen=True)
class ErrorEnvelope:
    type: ErrorType
    message: str
    retryable: bool

    def as_dict(self) -> dict:
        return {
            "error": {
                "type": self.type.value,
                "message": self.message,
                "retryable": self.retryable,
            }
        }


def classify_error(exc: Exception) -> ErrorEnvelope:
    if isinstance(exc, SensitiveDataError):
        return ErrorEnvelope(ErrorType.SENSITIVE_DATA, str(exc), False)
    if isinstance(exc, ConflictError):
        return ErrorEnvelope(ErrorType.CONFLICT, str(exc), False)
    if isinstance(exc, ConfigurationError):
        return ErrorEnvelope(ErrorType.CONFIGURATION, str(exc), False)
    if isinstance(exc, (EmbeddingError, StorageError, ProviderUnavailableError)):
        return ErrorEnvelope(ErrorType.UNAVAILABLE, str(exc), True)
    if isinstance(exc, ProviderResponseError):
        return ErrorEnvelope(ErrorType.INTERNAL, str(exc), False)
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return ErrorEnvelope(ErrorType.VALIDATION, str(exc), False)
    return ErrorEnvelope(ErrorType.INTERNAL, "internal CyberBrain error", False)


def not_found(message: str) -> ErrorEnvelope:
    return ErrorEnvelope(ErrorType.NOT_FOUND, message, False)
