<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError } from '@/api/http'
import { fetchHealth, fetchServiceInfo, type ServiceInfo } from '@/api/system'

type Status = 'checking' | 'online' | 'offline'

const status = ref<Status>('checking')
const serviceInfo = ref<ServiceInfo | null>(null)
const errorMessage = ref('')
const checkedAt = ref('')

async function check() {
  status.value = 'checking'
  errorMessage.value = ''
  serviceInfo.value = null
  try {
    await fetchHealth()
    serviceInfo.value = await fetchServiceInfo()
    status.value = 'online'
  } catch (err) {
    status.value = 'offline'
    errorMessage.value =
      err instanceof ApiError ? `[${err.code}] ${err.message}` : '未知错误，请查看后端日志'
  } finally {
    checkedAt.value = new Date().toLocaleString('zh-CN')
  }
}

onMounted(check)
</script>

<template>
  <h1 class="page-title">系统状态</h1>
  <p class="page-subtitle">用于验证前端页面与后端服务是否连通（M0 工程初始化的验收项之一）。</p>

  <div class="grid">
    <div class="stat">
      <div class="stat__label">前端</div>
      <div class="stat__value stat__value--ok">运行中</div>
    </div>
    <div class="stat">
      <div class="stat__label">后端服务</div>
      <div
        class="stat__value"
        :class="{
          'stat__value--ok': status === 'online',
          'stat__value--bad': status === 'offline',
          'stat__value--warn': status === 'checking',
        }"
      >
        {{ status === 'online' ? '连通' : status === 'offline' ? '不可用' : '检测中' }}
      </div>
    </div>
    <div class="stat">
      <div class="stat__label">最近检测时间</div>
      <div class="stat__value" style="font-size: 15px">{{ checkedAt || '—' }}</div>
    </div>
  </div>

  <section class="card" style="margin-top: 16px">
    <h2 class="card__title">后端服务信息</h2>
    <dl v-if="serviceInfo" class="kv">
      <dt>服务名称</dt>
      <dd>{{ serviceInfo.name }}</dd>
      <dt>版本</dt>
      <dd>{{ serviceInfo.version }}</dd>
      <dt>API 前缀</dt>
      <dd>{{ serviceInfo.api_prefix }}</dd>
      <dt>接口文档</dt>
      <dd>
        <a :href="serviceInfo.docs" target="_blank" rel="noreferrer">{{ serviceInfo.docs }}</a>
      </dd>
    </dl>
    <p v-else-if="status === 'offline'" class="note" style="color: var(--color-danger)">
      {{ errorMessage }}
    </p>
    <p v-else class="note">正在获取…</p>

    <button class="btn" style="margin-top: 12px" :disabled="status === 'checking'" @click="check">
      重新检测
    </button>
  </section>
</template>
