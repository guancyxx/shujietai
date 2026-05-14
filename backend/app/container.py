from __future__ import annotations
import os
from app.services.store_factory import build_store
from app.services.ingest_retry_service import IngestRetryService
from app.services.github_project_service import GitHubProjectService
from app.services.system_config_service import SystemConfigService
from app.services.dispatch_service import DispatchService
from app.services.dispatch_worker import DispatchWorkerPool
from app.services.task_lifecycle import TaskLifecycleService
from app.services.ws_manager import WsManager
from app.connectors.registry import register_defaults, list_platforms
from app.connectors.hermes import HermesConnectorAdapter


class _ConnectorAdapterRegistry:
    def __init__(self) -> None:
        self._adapters = {"hermes": HermesConnectorAdapter()}

    def get(self, name: str):
        return self._adapters[name]

    def names(self) -> list[str]:
        return sorted(set(self._adapters.keys()) | set(list_platforms()))


connector_registry = _ConnectorAdapterRegistry()
store = build_store()
github_project_service = GitHubProjectService()
config_session_factory = store.session_factory if hasattr(store, "session_factory") else None
system_config_service = SystemConfigService(config_session_factory)
register_defaults()
retry_service = None
retry_counters = {"ingest_success_total": 0, "ingest_retry_total": 0, "ingest_dlq_total": 0}
if hasattr(store, "session_factory"):
    retry_service = IngestRetryService(store.session_factory)

ws_manager = WsManager()
dispatch_service = DispatchService(store.session_factory) if hasattr(store, "session_factory") else None
worker_pool = DispatchWorkerPool(dispatch_service, ws_manager) if dispatch_service else None
lifecycle_service = TaskLifecycleService(
    session_factory=store.session_factory,
    dispatch_service=dispatch_service,
    worker_pool=worker_pool,
) if hasattr(store, "session_factory") and dispatch_service and worker_pool else None
