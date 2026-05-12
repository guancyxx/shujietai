# Fixed AI assistant provider selection spec

## Objective

The pinned AI assistant entry in the chat sidebar must let the user choose an AI provider / connector, not an LLM model provider. The selected value must be sent as the dispatch `ai_platform` value when starting a blank AI conversation.

## Problem

The current pinned assistant UI uses model-provider-oriented state and labels. That makes the dropdown appear to select an LLM provider, while the blank chat flow needs the platform connector used by the dispatch system.

## Scope

- Frontend only unless discovery shows the backend lacks a provider list endpoint.
- Preserve the existing pinned assistant visual placement and blank chat behavior.
- Do not change model selection or runtime preference behavior.
- Do not introduce browser-only verification; Docker build and endpoint smoke checks are sufficient.

## Expected behavior

- The pinned assistant dropdown label and state reflect AI provider/platform selection.
- The option list is derived from available dispatch AI providers when possible.
- Hermes remains the safe default.
- Starting a blank AI conversation uses the selected AI provider as `aiPlatform` / `ai_platform`.
- LLM model/provider selection remains separate and unchanged.

## Acceptance criteria

1. No pinned-assistant select in the chat sidebar uses LLM provider wording or `modelProviderDraft` state.
2. Blank chat dispatch payload uses the selected AI provider value.
3. The frontend build succeeds in Docker.
4. Running backend/frontend endpoints remain healthy after the change.

## Verification

- Static grep for pinned assistant provider bindings.
- Docker frontend build from the worktree.
- Main stack smoke endpoints: `/api/v1/health`, frontend `/`, `/api/v1/task-board`.
