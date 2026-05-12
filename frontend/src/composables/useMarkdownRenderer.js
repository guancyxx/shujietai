import { marked } from 'marked'
import DOMPurify from 'dompurify'

const MARKDOWN_CACHE_MAX = 200

export function useMarkdownRenderer() {
  const markdownCache = new Map()

  function renderMarkdown(text) {
    if (!text) return ''
    const cached = markdownCache.get(text)
    if (cached !== undefined) return cached
    const html = marked.parse(text, { breaks: true, gfm: true })
    const safe = DOMPurify.sanitize(html)
    if (markdownCache.size >= MARKDOWN_CACHE_MAX) {
      const firstKey = markdownCache.keys().next().value
      markdownCache.delete(firstKey)
    }
    markdownCache.set(text, safe)
    return safe
  }

  return { renderMarkdown }
}
