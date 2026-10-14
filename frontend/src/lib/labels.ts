/**
 * 业务枚举中文标签的**唯一来源**。
 *
 * 抽取自 StatusBadge.vue 原有的内联映射：状态徽章、床位态势图（ward-map）等
 * 展示层共用同一套词汇，避免同一枚举在不同页面出现不同叫法。
 * 这里只做「枚举值 -> 中文标签 + 语义色调」的映射，不包含任何业务规则。
 */

export type LabelKind =
  | 'bed'
  | 'priority'
  | 'admission'
  | 'allocation'
  | 'deposit'
  | 'bedType'
  | 'gender'

/** 值 -> [中文标签, 色调]。色调取值：ok / warn / info / muted / danger。 */
export const LABEL_MAPS: Record<LabelKind, Record<string, [string, string]>> = {
  bed: {
    AVAILABLE: ['空闲', 'ok'],
    RESERVED: ['预占用', 'warn'],
    OCCUPIED: ['已入住', 'info'],
    CLEANING: ['清洁中', 'muted'],
    MAINTENANCE: ['维护中', 'danger'],
  },
  priority: {
    CRITICAL: ['危重', 'danger'],
    SEVERE: ['重症', 'warn'],
    URGENT: ['急症', 'info'],
    NORMAL: ['普通', 'muted'],
    MILD: ['轻症', 'muted'],
  },
  admission: {
    DRAFT: ['草稿', 'muted'],
    ISSUED: ['已开具', 'info'],
    PRE_ADMITTED: ['待入院', 'warn'],
    ADMITTED: ['已入住', 'ok'],
    COMPLETED: ['已出院', 'muted'],
    CANCELLED: ['已取消', 'danger'],
  },
  allocation: {
    RESERVED: ['预占用', 'warn'],
    ADMITTED: ['已入住', 'ok'],
    DISCHARGED: ['已出院', 'muted'],
    CANCELLED: ['已取消', 'danger'],
  },
  deposit: {
    PENDING: ['待缴纳（模拟）', 'warn'],
    PAID: ['已缴纳（模拟）', 'ok'],
    REFUNDED: ['已退还（模拟）', 'muted'],
  },
  bedType: {
    NORMAL: ['普通床', 'muted'],
    ISOLATION: ['隔离床', 'danger'],
    MONITOR: ['监护床', 'info'],
  },
  gender: {
    MALE: ['男', 'info'],
    FEMALE: ['女', 'warn'],
    ANY: ['不限', 'muted'],
  },
}

/** 取某个枚举值的中文标签；未知值与空值分别回退到 fallback / 原值 / '—'。 */
export function labelOf(
  kind: LabelKind,
  value: string | null | undefined,
  fallback?: string | null,
): string {
  const key = value ?? ''
  return fallback || LABEL_MAPS[kind]?.[key]?.[0] || key || '—'
}

/** 取某个枚举值的语义色调；未知值回退到 muted。 */
export function toneOf(kind: LabelKind, value: string | null | undefined): string {
  return LABEL_MAPS[kind]?.[value ?? '']?.[1] ?? 'muted'
}
