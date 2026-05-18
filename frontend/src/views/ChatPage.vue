<script setup>
import ChatSessionList from '../components/chat/ChatSessionList.vue'
import ChatTimeline from '../components/chat/ChatTimeline.vue'
import ChatComposer from '../components/chat/ChatComposer.vue'
</script>

<template>
  <section class="main-grid chat-grid">
    <ChatSessionList />
    <article class="panel timeline-panel">
      <ChatTimeline />
      <ChatComposer />
    </article>
  </section>
</template>
