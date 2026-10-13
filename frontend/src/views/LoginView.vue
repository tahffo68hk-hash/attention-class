<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { useAuth } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const { signIn } = useAuth()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const errorMessage = ref('')

const demoAccounts = [
  { username: 'admin', password: 'admin123', label: '系统管理员' },
  { username: 'doctor01', password: 'doctor123', label: '医生（张明）' },
  { username: 'nurse01', password: 'nurse123', label: '护士（王芳）' },
  { username: 'viewer01', password: 'viewer123', label: '只读用户' },
]

function fill(username: string, password: string) {
  form.username = username
  form.password = password
}

async function submit() {
  if (!form.username || !form.password) {
    errorMessage.value = '请输入用户名与口令'
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    await signIn(form.username, form.password)
    const redirect = (route.query.redirect as string) || '/dashboard'
    await router.replace(redirect)
  } catch (err) {
    errorMessage.value =
      err instanceof ApiError ? `[${err.code}] ${err.message}` : '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card card">
      <h1 class="page-title" style="font-size: 18px">医院床位智能分配与住院入院预办理系统</h1>
      <p class="page-subtitle">请使用演示账号登录管理后台（仅虚构数据）</p>

      <div v-if="errorMessage" class="alert alert--danger">{{ errorMessage }}</div>

      <form @submit.prevent="submit">
        <div class="field" style="margin-bottom: 12px">
          <label for="username">用户名</label>
          <input id="username" v-model="form.username" class="input" autocomplete="username" />
        </div>
        <div class="field" style="margin-bottom: 16px">
          <label for="password">口令</label>
          <input
            id="password"
            v-model="form.password"
            class="input"
            type="password"
            autocomplete="current-password"
          />
        </div>
        <button class="btn btn--primary" style="width: 100%" :disabled="loading">
          {{ loading ? '登录中…' : '登 录' }}
        </button>
      </form>

      <div style="margin-top: 20px">
        <div class="note" style="margin-bottom: 6px">演示账号（点击填充）：</div>
        <div>
          <button
            v-for="acc in demoAccounts"
            :key="acc.username"
            class="btn btn--sm"
            type="button"
            @click="fill(acc.username, acc.password)"
          >
            {{ acc.label }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 420px;
  margin: 0;
}
</style>
