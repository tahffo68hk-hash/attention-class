/**
 * 病区床位态势图（Ward Map V1 数据契约 + V2 场景渲染）前端类型与派生规则。
 *
 * 说明（与交付包的差异，属有意为之）：
 * - 中文标签统一从 `@/lib/labels` 取（与床位管理页共用同一套词汇），
 *   不在此处另立一套叫法；十六进制色值仍由本模块维护，供 Three.js 场景使用。
 * - `simulated_position` 仅为教学模拟空间排布，**不是**真实医院平面图，
 *   也不用于床位评分（评分用的是 beds.position_x / position_y）。
 * - V2 只替换**场景渲染器**：线上契约仍是 `SIMULATED_GRID_V1`，
 *   三维位置由 scene-layout.ts 从上述模拟坐标确定性推导。
 */

import { labelOf } from '@/lib/labels'

export type BedState = 'AVAILABLE' | 'RESERVED' | 'OCCUPIED' | 'CLEANING' | 'MAINTENANCE'

/** V2 观察模式：整栋剖面 / 单层聚焦 / 分层展开。 */
export type SceneMode = 'building' | 'focus' | 'exploded'

export interface Position {
  x: number
  z: number
}

export interface WardRoom {
  ward_id: number
  code: string
  name: string
  department_id: number
  department_name: string
  building: string
  floor: number
  simulated_position: Position
  bed_count: number
}

export interface WardPatient {
  masked_name: string
  priority: string | null
  allocation_status: 'RESERVED' | 'ADMITTED'
  admission_request_id: number
}

export interface WardBed {
  id: number
  code: string
  status: BedState
  bed_type: string
  is_isolation: boolean
  ward_id: number
  ward_code: string
  ward_name: string
  department_id: number
  department_name: string
  floor: number
  building: string
  simulated_position: Position
  /**
   * 正式持久化的**展示槽位**（房间网格位）与朝向。
   * 只服务于三维编辑/管理的展示几何，**与评分用的 position_x/position_y 无关**。
   */
  scene_slot?: number | null
  scene_rotation?: number | null
  patient: WardPatient | null
  state_warning: string | null
}

export interface WardMapSnapshot {
  layout_kind: 'SIMULATED_GRID_V1'
  data_source: 'BUSINESS_API' | 'SYNTHETIC_DEMO'
  generated_at: string
  rooms: WardRoom[]
  beds: WardBed[]
  counts: Record<BedState, number>
}

export interface BedStatusMeta {
  label: string
  /** 供 3D 场景与图例使用的固定色值 */
  hex: string
  muted: string
  glyph: string
}

export const stateOrder: BedState[] = [
  'AVAILABLE',
  'RESERVED',
  'OCCUPIED',
  'CLEANING',
  'MAINTENANCE',
]

export const statusMeta: Record<BedState, BedStatusMeta> = {
  AVAILABLE: { label: labelOf('bed', 'AVAILABLE'), hex: '#2EAD84', muted: '#E2F8EF', glyph: '○' },
  RESERVED: { label: labelOf('bed', 'RESERVED'), hex: '#4C88E8', muted: '#E6F0FF', glyph: '◷' },
  OCCUPIED: { label: labelOf('bed', 'OCCUPIED'), hex: '#EAA04B', muted: '#FFF1DC', glyph: '●' },
  CLEANING: { label: labelOf('bed', 'CLEANING'), hex: '#9675D9', muted: '#F1EAFF', glyph: '✧' },
  MAINTENANCE: { label: labelOf('bed', 'MAINTENANCE'), hex: '#8793A3', muted: '#EEF1F5', glyph: '◇' },
}

/**
 * 只有「已入住状态 + ADMITTED 分配 + 无状态矛盾」三者同时成立才渲染人物几何体。
 * 预占只画半透明标志，不伪造真人；状态异常由页面显式告警。
 */
export function isConfirmedOccupant(b: WardBed): boolean {
  return b.status === 'OCCUPIED' && b.patient?.allocation_status === 'ADMITTED' && !b.state_warning
}

export function filterMap(
  beds: WardBed[],
  department: number,
  ward: number,
  floor: string,
  status: string,
  text: string,
): WardBed[] {
  const keyword = text.trim().toLowerCase()
  return beds.filter(
    (b) =>
      (!department || b.department_id === department) &&
      (!ward || b.ward_id === ward) &&
      (!floor || `${b.building}·${b.floor}` === floor) &&
      (!status || b.status === status) &&
      (!keyword || `${b.code} ${b.ward_code} ${b.ward_name}`.toLowerCase().includes(keyword)),
  )
}
