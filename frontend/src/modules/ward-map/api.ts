/**
 * 病区床位态势图的数据访问层。
 *
 * 交付包自带 `src/lib/api.ts`（单文件封装），本仓库的约定是 `src/api/*.ts` 分层 +
 * localStorage 会话；这里做薄适配，不新建第二套 HTTP 客户端：
 * - 快照：GET /api/v1/ward-map（仅此一个只读接口）
 * - 床位状态流水：复用既有 `fetchBedStatusLogs`，避免重复实现鉴权/错误处理
 *
 * 本模块**只读**：不调用任何写接口，不修改床位状态、分配或评分。
 */

import { fetchBedStatusLogs } from '@/api/business'
import http from '@/api/http'
import type { BedStatusLogRead } from '@/api/types'

import type { WardMapSnapshot } from './types'

/** 全院床位态势快照（后端仅登录鉴权，不区分角色）。 */
export async function fetchWardMap(): Promise<WardMapSnapshot> {
  const { data } = await http.get<WardMapSnapshot>('/api/v1/ward-map')
  return data
}

/** 单张床位的状态流水（与床位管理页共用同一接口）。 */
export async function fetchBedLogs(bedId: number, limit = 30): Promise<BedStatusLogRead[]> {
  return fetchBedStatusLogs(bedId, limit)
}
