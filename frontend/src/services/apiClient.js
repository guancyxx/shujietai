export async function parseErrorDetail(response) {
  let detail = ''
  try {
    const data = await response.json()
    detail = typeof data?.detail === 'string' ? data.detail : JSON.stringify(data?.detail || data || '')
  } catch {
    try {
      detail = (await response.text()) || ''
    } catch {
      detail = ''
    }
  }
  return detail.trim()
}

export function mapApiError(status, detail) {
  const normalized = String(detail || '').toLowerCase()
  if (status === 503 && normalized.includes('gh_cli_unavailable')) {
    return 'GitHub service is temporarily unavailable (gh CLI missing in backend). Please contact admin or retry later.'
  }
  if (status === 503 && normalized.includes('github_repo_create_unavailable')) {
    return 'GitHub repo creation is unavailable: both gh CLI and token fallback are not ready. Please configure token or backend runtime.'
  }
  if (status === 503 && normalized.includes('github_api_failed')) {
    return 'GitHub API is temporarily unavailable. Please retry in a moment.'
  }
  if (status === 401 || normalized.includes('bad credentials') || normalized.includes('requires authentication')) {
    return 'GitHub authentication failed. Please update GitHub token in system config.'
  }
  if (status === 422) {
    return `Validation failed: ${detail || 'invalid request payload'}`
  }
  if (detail) {
    return `Request failed: ${status} (${detail})`
  }
  return `Request failed: ${status}`
}

async function parseJsonResponse(response) {
  if (!response.ok) {
    const detail = await parseErrorDetail(response)
    throw new Error(mapApiError(response.status, detail))
  }
  return response.json()
}

export async function fetchJson(url) {
  return parseJsonResponse(await fetch(url))
}

export async function postJson(url, payload) {
  return parseJsonResponse(await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function postJsonTimeout(url, payload, timeoutMs) {
  const controller = new AbortController()
  const id = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await parseJsonResponse(await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    }))
  } finally {
    clearTimeout(id)
  }
}

export async function putJson(url, payload) {
  return parseJsonResponse(await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function patchJson(url, payload) {
  return parseJsonResponse(await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function deleteJson(url) {
  return parseJsonResponse(await fetch(url, { method: 'DELETE' }))
}
