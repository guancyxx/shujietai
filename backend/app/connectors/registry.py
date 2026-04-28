from __future__ import annotations

from app.connectors.hermes import HermesConnectorAdapter


class ConnectorRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, object] = {}

    def register(self, connector_name: str, adapter: object) -> None:
        self._adapters[connector_name] = adapter

    def get(self, connector_name: str) -> object:
        adapter = self._adapters.get(connector_name)
        if adapter is None:
            raise KeyError(f"connector_not_registered:{connector_name}")
        return adapter


def build_default_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register("hermes", HermesConnectorAdapter())
    return registry
