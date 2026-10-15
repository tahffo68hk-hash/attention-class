/**
 * 参数化建筑空间推导 —— 纯展示层几何，**不是** BIM，也不是临床/评分坐标。
 *
 * 与 V2 的区别（Spatial / Simulation V1）：
 * - V2 直接采用后端 `simulated_position` 的散点定位逐点摆放，房间不会对齐，
 *   各楼层也各有各的宽度与走廊位置；
 * - 本版改为**参数化布局**：每栋楼按病区归属、楼层、房间编号自然排序，
 *   所有楼层共用同一建筑宽度、走廊轴线、双侧病房模块与层高；
 *   房间沿中央走廊（`corridorZ`）两侧镜像成排，房门朝向走廊，
 *   床位在房内按床号排序、每间三列、南北病房分别朝外侧墙体。
 *   因此**完全忽略** `simulated_position` —— 那批坐标本来也不是真实位置。
 *
 * 契约边界：
 * - 后端 `layout_kind` 仍为 `SIMULATED_GRID_V1`，空间仍是模拟排布；
 * - 床位评分用的是 `beds.position_x / position_y`，与本文件无关；
 * - 布局对入参顺序**不敏感**（排序后才落位），同一份快照必得同一组坐标，
 *   由 `verify_spatial_simulation.cjs` 与 `verify_v2_layout.cjs` 双向校验；
 * - 第三参数 `poses` 只服务于**模拟编辑草稿**（槽位吸附 + 旋转增量），
 *   它改变的是展示几何，不会写回任何业务表，也不会进入评分。
 */

import type { WardBed, WardRoom } from './types'

/** 层高（展示单位）。真实建筑层高约 3~4m，这里为剖面可读性放大。 */
export const FLOOR_HEIGHT = 4.9

/** 病房开间（展示单位）。 */
export const ROOM_WIDTH = 12.2

/** 中央走廊宽度（展示单位）。 */
export const CORRIDOR_WIDTH = 4.5

/** 楼板外沿留边 / 病房模块间距 / 房内床位排布参数（均为模拟比例，不是米）。 */
const EDGE = 1.05
const ROOM_GAP = 0.35
const BED_COLUMNS = 3
const BED_PITCH_X = 3.08
const BED_PITCH_Z = 3.4

export type RoomSide = 'north' | 'south'

export interface SceneRoom {
  room: WardRoom
  x: number
  z: number
  width: number
  depth: number
  /** 位于中央走廊的哪一侧；决定房门朝向与床位朝向 */
  side: RoomSide
}

export interface SceneBed {
  bed: WardBed
  x: number
  z: number
  floorKey: string
  /** 床位绕 Y 轴旋转：床头朝外侧墙体（南侧病房旋转 π） */
  orientation: number
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
  /** 中央走廊轴线（楼层局部 Z） */
  corridorZ: number
  corridorWidth: number
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

export function floorKey(building: string, floor: number): string {
  return `${building}·${floor}`
}

/** 自然序比较：`10-2` 排在 `10-10` 之前，避免字典序把房号排乱。 */
const compare = (a: string, b: string) => a.localeCompare(b, 'zh-CN', { numeric: true })

export function createHospitalPlan(
  rooms: WardRoom[],
  beds: WardBed[],
  /** 模拟编辑草稿的槽位姿态（床位 id -> 病房/槽位/旋转）。缺省时按床号顺排。 */
  poses: Record<number, { wardId: number; slot: number; rotation: number }> = {},
): HospitalPlan {
  const grouped = new Map<string, Map<number, WardRoom[]>>()
  for (const room of rooms) {
    let floors = grouped.get(room.building)
    if (!floors) {
      floors = new Map()
      grouped.set(room.building, floors)
    }
    const list = floors.get(room.floor) || []
    list.push(room)
    floors.set(room.floor, list)
  }
  const byRoom = new Map<number, WardBed[]>()
  for (const bed of beds) {
    const list = byRoom.get(bed.ward_id) || []
    list.push(bed)
    byRoom.set(bed.ward_id, list)
  }

  const buildings: SceneBuilding[] = []
  const floors: SceneFloor[] = []
  const bedFloors: HospitalPlan['bedFloors'] = {}
  const bedLocations: HospitalPlan['bedLocations'] = {}
  let buildingX = 0

  // 建筑按名称排序 → 与传入顺序无关，保证布局稳定
  for (const [name, floorMap] of [...grouped].sort((a, b) => compare(a[0], b[0]))) {
    const ordered = [...floorMap].sort((a, b) => a[0] - b[0])
    // 同一栋楼的**所有楼层**共用同一套建筑轮廓与房间纵向轴线：
    // 开间数取该楼任何一层的最大值，进深取该楼最深的病房，走廊轴线因此逐层对齐。
    const bays = Math.max(1, ...ordered.map(([, rs]) => Math.ceil(rs.length / 2)))
    const maxRows = Math.max(
      1,
      ...rooms
        .filter((r) => r.building === name)
        .map((r) => Math.ceil((byRoom.get(r.ward_id)?.length || 0) / BED_COLUMNS)),
    )
    const roomDepth = Math.max(9.6, maxRows * BED_PITCH_Z + 3.0)
    const width = EDGE * 2 + bays * (ROOM_WIDTH + ROOM_GAP) - ROOM_GAP
    const depth = EDGE * 2 + roomDepth * 2 + CORRIDOR_WIDTH
    const corridorZ = EDGE + roomDepth + CORRIDOR_WIDTH / 2

    const buildingFloors: SceneFloor[] = []
    for (const [index, [floor, rs]] of ordered.entries()) {
      const sortedRooms = [...rs].sort((a, b) => compare(a.code, b.code) || a.ward_id - b.ward_id)
      const key = floorKey(name, floor)
      const sceneRooms: SceneRoom[] = []
      const sceneBeds: SceneBed[] = []

      sortedRooms.forEach((room, i) => {
        // 交替分配到走廊北侧 / 南侧，沿建筑纵向轴线镜像成排
        const bay = Math.floor(i / 2)
        const side: RoomSide = i % 2 === 0 ? 'north' : 'south'
        const x = EDGE + bay * (ROOM_WIDTH + ROOM_GAP)
        const z = side === 'north' ? EDGE : EDGE + roomDepth + CORRIDOR_WIDTH
        sceneRooms.push({ room, x, z, width: ROOM_WIDTH, depth: roomDepth, side })

        const items = [...(byRoom.get(room.ward_id) || [])].sort(
          (a, b) => compare(a.code, b.code) || a.id - b.id,
        )
        items.forEach((bed, j) => {
          // 编辑草稿的槽位姿态优先于「按床号顺排」的默认落位：槽位是屏幕网格吸附
          // 位置，不是医疗评分坐标；同样，旋转增量只是叠加在「床头朝外侧墙」的基准角上。
          const pose = poses[bed.id]
          const slot = pose && pose.wardId === room.ward_id ? pose.slot : j
          const col = slot % BED_COLUMNS
          const row = Math.floor(slot / BED_COLUMNS)
          const bedX = x + 2.35 + col * BED_PITCH_X
          // 北侧病房的床头朝外侧（-Z）墙；南侧整房旋转 π，床头同样朝外侧墙。
          const bedZ =
            side === 'north' ? z + 1.9 + row * BED_PITCH_Z : z + roomDepth - 1.9 - row * BED_PITCH_Z
          const orientation =
            (side === 'north' ? 0 : Math.PI) + ((pose?.rotation || 0) * Math.PI) / 180
          sceneBeds.push({ bed, x: bedX, z: bedZ, floorKey: key, orientation })
          bedFloors[bed.id] = key
          // 轻微 Z 错层，避免上下层床位在正交视角下完全重叠
          bedLocations[bed.id] = {
            x: buildingX + bedX,
            y: index * FLOOR_HEIGHT + 0.62,
            z: bedZ - index * 0.35,
          }
        })
      })

      const item: SceneFloor = {
        key,
        building: name,
        floor,
        index,
        x: buildingX,
        width,
        depth,
        corridorZ,
        corridorWidth: CORRIDOR_WIDTH,
        rooms: sceneRooms,
        beds: sceneBeds,
      }
      buildingFloors.push(item)
      floors.push(item)
    }

    buildings.push({ name, x: buildingX, width, depth, floors: buildingFloors })
    // 建筑之间留出通廊间距
    buildingX += width + 8
  }

  return { buildings, floors, bedFloors, bedLocations }
}
