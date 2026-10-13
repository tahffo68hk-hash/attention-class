<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <h1 class="page-title">页面不存在</h1>
  <p class="page-subtitle">请求的地址未在路由表中注册。</p>
  <RouterLink class="btn" to="/" style="display: inline-block">返回项目首页</RouterLink>
</template>
