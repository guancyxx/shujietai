# Spec: Chunk Handler Registry for dispatch_worker.py

## Objective

Replace the 7-branch if/elif chain in `TaskWorker._execute_ai_call()` (lines 261-416) with a handler registry pattern to satisfy the Open/Closed Principle. New chunk types must be addable without modifying the dispatch method.

## Current State

`_execute_ai_call()` iterates over `connector.stream_completion()` chunks and dispatches via if/elif on `chunk_type`:

| Chunk Type | Lines | Behavior |
|---|---|---|
| `content` / `content_delta` | 263-274 | Accumulate content, emit `content_delta` event |
| `tool_call` | 276-317 | Track in-flight tool calls, emit `tool_call` start/delta events |
| `finish` | 319-344 | Finalize all in-flight tool calls, emit progress with usage |
| `tool_start` | 346-366 | Initialize in-flight tool tracking, emit `tool_call` start |
| `tool_complete` | 368-402 | Match in-flight tool by ID/name, emit `tool_call` completed |
| `agent_thinking` | 404-413 | Emit `agent_thinking` event with reasoning text |
| `error` | 415-416 | Raise RuntimeError |

Each branch accesses `self._task`, `self._cancelled`, `self._tool_calls_in_flight`, `self._emit_event()`, and the `full_content` local accumulator.

## Target Pattern: Handler Registry

A `ChunkHandler` protocol and a registry dict keyed by chunk type. The `_execute_ai_call()` loop becomes:

```
async for chunk in connector.stream_completion(...):
    handler = self._chunk_handlers.get(chunk_type)
    if handler:
        await handler(chunk, ctx)
```

Where `ctx` is a lightweight dataclass holding the shared mutable state needed by handlers (`full_content`, `tool_calls_in_flight`, `cancelled` flag).

### Handler Signature

```python
ChunkHandler = Callable[[dict[str, Any], ChunkContext], Coroutine[Any, Any, None]]
```

### ChunkContext

```python
@dataclass
class ChunkContext:
    full_content: str              # mutable accumulator
    tool_calls_in_flight: dict     # shared in-flight tool state
    cancelled: bool                # read by handlers to early-exit
    task: DispatchTaskItem          # read-only task metadata
    emit_event: Callable           # self._emit_event bound method
```

## Design Decisions

1. **ChunkContext is a dataclass, not a dict**: Type-safe, explicit fields, IDE support.
2. **Handlers are methods on TaskWorker, not standalone functions**: They need `self` for `_emit_event` and `_task`. The registry maps chunk_type strings to bound methods.
3. **full_content accumulator lives in ChunkContext, not self**: Keeps handler state scoped to the streaming session. TaskWorker persists `self._tool_calls_in_flight` and `self._cancelled` because they survive beyond a single connector call (interrupt/resume).
4. **Registry is a class-level dict**: `TaskWorker._chunk_handlers: ClassVar[dict]` built once at class definition, not per instance.
5. **`finish` handler must also handle `full_content` accumulation finalization**: The `finish` handler emits tool completions and progress events; the `content_full` event and `_write_assistant_to_store` call happen AFTER the loop, not inside a handler.

## TaskWorker Changes

### New class-level constant

```python
class TaskWorker:
    _chunk_handlers: ClassVar[dict[str, Callable[..., Coroutine]]]    
```

### New ChunkContext

```python
@dataclass
class ChunkContext:
    """Mutable context shared across chunk handlers during one streaming call."""
    full_content: str = ""
    tool_calls_in_flight: dict[str, dict[str, Any]] = field(default_factory=dict)
    cancelled: bool = False
```

### New handler methods (extracted from if/elif branches)

- `_handle_content(chunk, ctx)` — content/content_delta
- `_handle_tool_call(chunk, ctx)` — tool_call streaming
- `_handle_finish(chunk, ctx)` — finish
- `_handle_tool_start(chunk, ctx)` — tool_start
- `_handle_tool_complete(chunk, ctx)` — tool_complete
- `_handle_agent_thinking(chunk, ctx)` — agent_thinking
- `_handle_error(chunk, ctx)` — error

### Modified _execute_ai_call

The if/elif chain (lines 261-416) becomes:

```python
ctx = ChunkContext(
    tool_calls_in_flight=self._tool_calls_in_flight,
    cancelled=self._cancelled,
)

async for chunk in connector.stream_completion(messages, config):
    if self._cancelled:
        return
    
    chunk_type = chunk.get("type")
    handler = self._chunk_handlers.get(chunk_type)
    if handler is not None:
        ctx.cancelled = self._cancelled  # sync before each handler
        await handler(chunk, ctx)
```

### Registry initialization

```python
_chunk_handlers = {
    "content": _handle_content,
    "content_delta": _handle_content,
    "tool_call": _handle_tool_call,
    "finish": _handle_finish,
    "tool_start": _handle_tool_start,
    "tool_complete": _handle_tool_complete,
    "agent_thinking": _handle_agent_thinking,
    "error": _handle_error,
}
```

Note: Both `content` and `content_delta` map to `_handle_content` — the existing code already treats them identically.

## Files Touched

- `backend/app/services/dispatch_worker.py` — main change

## Boundaries

- Always: preserve all existing event emission behavior, tool tracking logic, and error handling
- Ask first: adding new chunk types without task-board item
- Never: change the public API of `TaskWorker.run()`, `_emit_event()`, or connector contracts

## Success Criteria

1. All 7 chunk types handled through registry, zero if/elif branches remain in the loop
2. Each handler is a named method with a clear single responsibility
3. Adding a new chunk type requires only: (a) write a handler method, (b) add one line to `_chunk_handlers` dict
4. Existing dispatch behavior is preserved: same events, same tool tracking, same error semantics
5. Backend Docker build succeeds
6. All existing dispatch tests pass (or manual dispatch test succeeds)

## Open Questions

None — task board item is self-contained with clear scope.
