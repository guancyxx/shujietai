"""AI connector protocol for dispatch orchestration (ADR-0004 Step 3).

Each AI platform must implement StreamingAIConnector.
The DispatchWorker delegates the actual API calls to the appropriate connector.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class StreamingAIConnector(Protocol):
    """Protocol for AI connectors that support streaming completions."""

    platform_name: str

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        config: dict,
    ) -> AsyncIterator[dict]:
        """Stream AI completion chunks.

        Each yielded dict has one of:
          - {"type": "content", "content": str}
          - {"type": "tool_call", "function_name": str, "function_args_delta": str, "index": int, "id": str}
          - {"type": "finish", "finish_reason": str, "usage": dict}
          - {"type": "error", "error": str}

        The caller (TaskWorker) handles events, state transitions, and broadcasting.
        """
        ...