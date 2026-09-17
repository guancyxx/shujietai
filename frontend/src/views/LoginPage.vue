<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { postJson } from '../services/apiClient.js'
import { setSession } from '../services/auth.js'

const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:18000'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const errorMessage = ref('')
const submitting = ref(false)

async function submitLogin() {
  errorMessage.value = ''
  if (!username.value.trim() || !password.value) {
    errorMessage.value = '请输入用户名和密码'
    return
  }
  submitting.value = true
  try {
    const data = await postJson(`${apiBase}/api/auth/login`, {
      username: username.value.trim(),
      password: password.value,
    })
    setSession(data.access_token, data.username)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(redirect)
  } catch (error) {
    errorMessage.value = error?.message?.includes('invalid_credentials')
      ? '用户名或密码错误'
      : (error?.message || '登录失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-shell">
    <div class="bg-layer"></div>
    <section class="login-card" aria-label="登录">
      <div class="login-brand">
        <img class="login-logo" src="/src/assets/logo-sjt-a3-icon.svg" alt="枢界台 Logo" />
        <h1 class="login-title">枢界台</h1>
        <p class="login-subtitle">会话驾驶 cockpit · 请登录以继续</p>
      </div>

      <form class="login-form" @submit.prevent="submitLogin">
        <label class="login-field">
          <span class="login-label">用户名</span>
          <input
            v-model="username"
            type="text"
            name="username"
            autocomplete="username"
            placeholder="username"
            :disabled="submitting"
          />
        </label>
        <label class="login-field">
          <span class="login-label">密码</span>
          <input
            v-model="password"
            type="password"
            name="password"
            autocomplete="current-password"
            placeholder="••••••••"
            :disabled="submitting"
          />
        </label>

        <p v-if="errorMessage" class="login-error" role="alert">{{ errorMessage }}</p>

        <button class="login-submit" type="submit" :disabled="submitting">
          {{ submitting ? '登录中…' : '登 录' }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
/* Neumorphic 暖黑 + 金 登录卡（M1）— 页面级样式，按 style-layering-spec 归属本组件 */
.login-shell {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #14110e;
  overflow: hidden;
}

.login-card {
  position: relative;
  z-index: 1;
  width: min(400px, calc(100vw - 48px));
  padding: 44px 40px 40px;
  border-radius: 24px;
  background: linear-gradient(145deg, #17130f, #110e0b);
  box-shadow:
    10px 10px 28px rgba(0, 0, 0, 0.55),
    -10px -10px 28px rgba(255, 228, 178, 0.05),
    inset 0 0 0 1px rgba(211, 160, 67, 0.14);
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.login-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.login-logo {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  box-shadow:
    6px 6px 14px rgba(0, 0, 0, 0.5),
    -4px -4px 12px rgba(255, 228, 178, 0.06);
}

.login-title {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 4px;
  color: #d3a043;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
}

.login-subtitle {
  margin: 0;
  font-size: 13px;
  color: rgba(238, 226, 204, 0.55);
  letter-spacing: 1px;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.login-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.login-label {
  font-size: 12px;
  letter-spacing: 2px;
  color: rgba(211, 160, 67, 0.85);
}

.login-field input {
  padding: 13px 16px;
  border: none;
  border-radius: 14px;
  background: #14110e;
  color: #f3ead9;
  font-size: 15px;
  outline: none;
  box-shadow:
    inset 5px 5px 10px rgba(0, 0, 0, 0.55),
    inset -4px -4px 10px rgba(255, 228, 178, 0.04);
  transition: box-shadow 0.2s ease;
}

.login-field input::placeholder {
  color: rgba(238, 226, 204, 0.28);
}

.login-field input:focus {
  box-shadow:
    inset 5px 5px 10px rgba(0, 0, 0, 0.55),
    inset -4px -4px 10px rgba(255, 228, 178, 0.04),
    0 0 0 2px rgba(211, 160, 67, 0.45);
}

.login-error {
  margin: 0;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 13px;
  color: #ffb08a;
  background: rgba(180, 70, 30, 0.14);
  box-shadow: inset 0 0 0 1px rgba(255, 140, 90, 0.25);
}

.login-submit {
  margin-top: 4px;
  padding: 14px;
  border: none;
  border-radius: 14px;
  cursor: pointer;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 8px;
  color: #14110e;
  background: linear-gradient(145deg, #e0b056, #c8922f);
  box-shadow:
    6px 6px 14px rgba(0, 0, 0, 0.5),
    -3px -3px 10px rgba(255, 228, 178, 0.08);
  transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
}

.login-submit:hover:not(:disabled) {
  filter: brightness(1.06);
  box-shadow:
    8px 8px 18px rgba(0, 0, 0, 0.55),
    -3px -3px 10px rgba(255, 228, 178, 0.1);
}

.login-submit:active:not(:disabled) {
  transform: translateY(1px);
}

.login-submit:disabled {
  cursor: not-allowed;
  filter: saturate(0.5) brightness(0.8);
}
</style>
