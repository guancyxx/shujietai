"""Connector registry — maps ai_platform name to StreamingAIConnector instance."""

from __future__ import annotations

import logging
from typing import Any

from app.connectors.ai_base import StreamingAIConnector
from app.connectors.hermes_streaming import HermesStreamingConnector

logger = logging.getLogger(__name__)

# Global singleton registry
_registry: dict[str, StreamingAIConnector] = {}


def register_connector(connector: StreamingAIConnector) -> None:
    """Register a connector. Its `platform_name` becomes the lookup key."""
    _registry[connector.platform_name] = connector
    logger.info("Registered AI connector: %s", connector.platform_name)


def get_connector(platform: str) -> StreamingAIConnector | None:
    """Look up a registered connector by platform name."""
    return _registry.get(platform)


def list_platforms() -> list[str]:
    """Return names of all registered platforms."""
    return list(_registry.keys())


def register_defaults() -> None:
    """Register the built-in connector set. Called once at app startup."""
    register_connector(HermesStreamingConnector())