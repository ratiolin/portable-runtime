"""Provider adapters shipped with the portable runtime."""

from .fake import EchoProvider, FailingProvider

__all__ = ["EchoProvider", "FailingProvider"]
