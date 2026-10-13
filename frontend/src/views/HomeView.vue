<script setup lang="ts">
const techStack = [
  { label: '前端', value: 'Vue 3 + TypeScript + Vite' },
  { label: '后端', value: 'FastAPI + SQLAlchemy + Alembic' },
  { label: '数据库', value: 'MySQL 8' },
  { label: '测试', value: 'pytest（含 MySQL 并发与权限用例）' },
  { label: '部署', value: 'Docker Compose' },
  { label: '架构', value: '模块化单体（不引入微服务）' },
]

const scope = [
  '基础数据管理：科室、病房、床位（性别限制 / 隔离属性 / 位置 / 状态）、患者、医生',
  '住院证开具与流转，记录病情优先级与隔离需求',
  '预入院登记、模拟预交金与待入院队列（不接入真实支付）',
  '智能床位推荐：硬约束过滤 + 可解释软约束评分',
  '床位分配：推荐确认 / 人工选择，事务与并发保护，全流程状态留痕',
  '管理看板与筛选、安全脱敏与操作审计',
]
</script>

<template>
  <h1 class="page-title">医院床位智能分配与住院入院预办理原型系统</h1>
  <p class="page-subtitle">
    面向医院住院处的原型系统：从开具住院证、预入院登记，到智能床位推荐与分配的全流程演示。
  </p>

  <section class="card">
    <h2 class="card__title">技术栈</h2>
    <dl class="kv">
      <template v-for="item in techStack" :key="item.label">
        <dt>{{ item.label }}</dt>
        <dd>{{ item.value }}</dd>
      </template>
    </dl>
  </section>

  <section class="card">
    <h2 class="card__title">系统范围</h2>
    <ul class="plain">
      <li v-for="item in scope" :key="item">{{ item }}</li>
    </ul>
  </section>

  <section class="card">
    <h2 class="card__title">当前阶段</h2>
    <p>
      <span class="tag tag--ok">M0 工程初始化 已完成</span>
      <span class="tag tag--info">前端骨架</span>
      <span class="tag tag--info">后端骨架</span>
      <span class="tag tag--info">数据库迁移</span>
      <span class="tag tag--warn">业务功能迭代中</span>
    </p>
    <p class="note">
      本系统仅使用虚构患者数据，不含真实医疗数据、真实支付与付费 AI 服务。
    </p>
  </section>
</template>
