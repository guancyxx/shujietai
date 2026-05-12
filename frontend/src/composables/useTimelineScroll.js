import { nextTick, ref } from 'vue'

export function useTimelineScroll() {
  const timelineScrollRef = ref(null)
  const userScrolledUp = ref(false)

  function scrollToBottom(force = false) {
    if (!timelineScrollRef.value) return
    if (!force && userScrolledUp.value) return
    nextTick(() => {
      const el = timelineScrollRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }

  function onTimelineScroll() {
    const el = timelineScrollRef.value
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    userScrolledUp.value = !atBottom
  }

  function resetTimelineScroll() {
    userScrolledUp.value = false
    scrollToBottom(true)
  }

  return {
    timelineScrollRef,
    userScrolledUp,
    scrollToBottom,
    onTimelineScroll,
    resetTimelineScroll,
  }
}
