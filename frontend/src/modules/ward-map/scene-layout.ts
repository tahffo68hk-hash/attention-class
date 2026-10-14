/**
 * Hospital Vision V2 —— 纯展示层的空间推导（**不是** BIM，也不是临床坐标）。
 *
 * 与后端契约的关系：
 * - `layout_kind` 仍然是 `SIMULATED_GRID_V1`：V2 换的是**场景渲染器**，
 *   不代表拿到了真实医院/建筑空间数据；
 * - 所有三维位置都由 V1 的 `simulated_position`（房间/床位）确定性推导，
 *   因此同一份快照无论查询顺序如何都得到完全相同的坐标（verify_v2_layout.cjs 校验）；
 * - 楼层实体化（每层抬升 FLOOR_HEIGHT）是纯视觉表达，不参与床位评分
 *   （评分用的是 beds.position_x / position_y）。
 */

import type { WardBed, WardRoom } from './types'

/** 层高（视觉单位）。真实建筑层高约 3~4m，这里为剖面可读性放大。 */
export const FLOOR_HEIGHT = 4.9

/** 病房开间（视觉单位），对应 demo/后端模拟网格里 4 张床的横向跨度。 */
export const ROOM_WIDTH = 10.3

export function floorKey(building: string, floor: number): string {
  return `${building}·${floor}`
}

export interface SceneRoom {
  room: WardRoom
  x: number
  z: number
  width: number
  depth: number
}

export interface SceneBed {
  bed: WardBed
  x: number
  z: number
  floorKey: string
}

export interface SceneFloor {
  key: string
  building: string
  floor: number
  /** 在本建筑内的层序（从 0 起），决定 Y 抬升 */
  index: number
  /** 本建筑内的 X 偏移（多建筑横向并列） */
  x: number
  width: number
  depth: number
  rooms: SceneRoom[]
  beds: SceneBed[]
}

export interface SceneBuilding {
  name: string
  x: number
  width: number
  depth: number
  floors: SceneFloor[]
}

export interface HospitalPlan {
  buildings: SceneBuilding[]
  floors: SceneFloor[]
  /** 床位 id -> 所属楼层 key */
  bedFloors: Record<number, string>
  /** 床位 id -> 建筑级世界坐标（用于镜头定位与床位检索） */
  bedLocations: Record<number, { x: number; y: number; z: number }>
}

export function createHospitalPlan(rooms: WardRoom[], beds: WardBed[]): HospitalPlan {
  const buildingGroups = new Map<string, Map<number, WardRoom[]>>()
  for (const r of rooms) {
    let floors = buildingGroups.get(r.building)
    if (!floors) {
      floors = new Map()
      buildingGroups.set(r.building, floors)
    }
    const group = floors.get(r.floor) || []
    group.push(r)
    floors.set(r.floor, group)
  }
  const byRoom = new Map<number, WardBed[]>()
  for (const b of beds) {
    const list = byRoom.get(b.ward_id) || []
    list.push(b)
    byRoom.set(b.ward_id, list)
  }

  const sceneBuildings: SceneBuilding[] = []
  const allFloors: SceneFloor[] = []
  const bedFloors: HospitalPlan['bedFloors'] = {}
  const bedLocations: HospitalPlan['bedLocations'] = {}
  let buildingX = 0

  // 建筑按名称排序 → 与传入顺序无关，保证布局稳定
  for (const [buildingName, floors] of [...buildingGroups.entries()].sort((a, b) =>
    a[0].localeCompare(b[0], 'zh-CN'),
  )) {
    const sorted = [...floors].sort((a, b) => a[0] - b[0])
    const buildingFloors: SceneFloor[] = []
    let maxWidth = 0
    let maxDepth = 0

    for (const [idx, [floor, rs]] of sorted.entries()) {
      const minX = Math.min(...rs.map((r) => r.simulated_position.x))
      const minZ = Math.min(...rs.map((r) => r.simulated_position.z))
      const roomList: SceneRoom[] = rs.map((r) => ({
        room: r,
        x: r.simulated_position.x - minX + 2.2,
        z: r.simulated_position.z - minZ + 2.2,
        width: ROOM_WIDTH,
        // 走廊 + 床位排布所需的最小进深；至少容得下一排 4 床 + 通道
        depth: Math.max(8.5, Math.ceil(r.bed_count / 4) * 3.25 + 3),
      }))
      const key = floorKey(buildingName, floor)

      const sceneBeds: SceneBed[] = []
      for (const r of rs) {
        for (const b of byRoom.get(r.ward_id) || []) {
          // 床位坐标按所属房间的局部排布换算到楼层坐标系：房间基准 + 房内偏移。
          // （与后端 ward_map.simulated_positions 的 `base_x/base_z + 偏移` 口径一致。）
          const bed = b.simulated_position
          const room = r.simulated_position
          const localX = bed.x - room.x
          const localZ = bed.z - room.z
          const item = {
            bed: b,
            x: room.x - minX + 2.2 + localX,
            z: room.z - minZ + 2.2 + localZ,
            floorKey: key,
          }
          sceneBeds.push(item)
          bedFloors[b.id] = key
          // 轻微 Z 错层，避免上下层床位在正交视角下完全重叠
          bedLocations[b.id] = { x: buildingX + item.x, y: idx * FLOOR_HEIGHT + 0.62, z: item.z - idx * 0.35 }
        }
      }

      // 楼板尺寸同时覆盖房间与床位：任何一侧算出越界都不会把床位甩到楼板外。
      const BED_MARGIN = 1.6
      const width = Math.max(
        17,
        ...roomList.map((r) => r.x + r.width + 2.2),
        ...sceneBeds.map((b) => b.x + BED_MARGIN + 2.2),
      )
      const depth = Math.max(
        14,
        ...roomList.map((r) => r.z + r.depth + 2.2),
        ...sceneBeds.map((b) => b.z + BED_MARGIN + 2.2),
      )

      const item: SceneFloor = {
        key,
        building: buildingName,
        floor,
        index: idx,
        x: buildingX,
        width,
        depth,
        rooms: roomList,
        beds: sceneBeds,
      }
      buildingFloors.push(item)
      allFloors.push(item)
      maxWidth = Math.max(width, maxWidth)
      maxDepth = Math.max(depth, maxDepth)
    }

    sceneBuildings.push({ name: buildingName, x: buildingX, width: maxWidth, depth: maxDepth, floors: buildingFloors })
    // 建筑之间留出通廊间距
    buildingX += maxWidth + 7.5
  }

  return { buildings: sceneBuildings, floors: allFloors, bedFloors, bedLocations }
}