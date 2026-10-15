<script setup lang="ts">
/**
 * 病区三维场景 —— Hospital Vision V2（Three.js 正交 2.5D 剖面）。
 *
 * 这是**可视化**组件，不代表真实建筑平面图：房间/床位坐标来自后端
 * SIMULATED_GRID_V1 的稳定模拟排布（scene-layout.ts 确定性推导），
 * 与床位评分使用的 beds.position_x / position_y 无关。
 *
 * 与交付包的差异（本地适配，均不改变 V2 的渲染语义）：
 *  1. 类型/布局引用改走 `@/modules/ward-map/*`（本仓库模块路径约定）；
 *  2. 画布改用**透明背景**（alpha），底色交给 ward-map.css 的设计令牌渐变，
 *     使明暗主题自动跟随，且省掉一份硬编码背景色；
 *  3. 新增 `dark` 属性：暗色主题下下调曝光，避免白色病房在深色底上刺眼；
 *  4. 打开方向光软阴影（阴影贴图仅在场景/楼层变化时重算），床位落在地面上，
 *     消除「悬浮方块」观感；透明玻璃不投影，因此不会在剖面里形成遮挡带；
 *  5. 患者几何下移贴合床垫与枕头，避免「人浮在床上/穿进床垫」；
 *  6. 合并 Hover Visual V3：按视线探测并淡化遮挡构件、床位弹性浮起、
 *     每床独立材质做发光/框线/床垫过渡；**保留**上述阴影、曝光与几何加固，
 *     并修掉交付包漏传 surfaceRest/surfaceHover 导致运行时报错的缺陷；
 *  7. Spatial / Simulation V1：建筑几何改由 scene-layout.ts 的参数化布局给出
 *     （中央走廊 + 走廊两侧镜像病房 + 门洞 + 床位按南北转向），
 *     并叠加只读沙盘的轮廓提示（候选青 / 模拟命中金 / 假设停用灰）。
 *     叠加层**只改描边**，床位五态主色与业务状态永不被覆盖。
 *
 * Hover V3 的实现要点（均为纯视觉，不触碰业务状态）：
 * - 拾取体固定挂在楼层 Group，可见病床单独沿 Y 浮起，动画不移动命中区域；
 * - 遮挡淡化只作用于「相机与被悬停床位之间」被射线穿过的构件，逐对象克隆材质，
 *   共享材质（同一状态的多张床）绝不会被就地改色；
 * - prefers-reduced-motion 下取消动画但保留状态与遮挡语义。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

import {
  FLOOR_HEIGHT,
  createHospitalPlan,
  type HospitalPlan,
  type SceneFloor,
} from '@/modules/ward-map/scene-layout'
import {
  HOVER_LIFT,
  easedApproach,
  fadedOccluderOpacity,
  isNear,
  sceneBedPalette,
  type OccluderKind,
} from '@/modules/ward-map/hover-visual'
import { isConfirmedOccupant, statusMeta } from '@/modules/ward-map/types'
import type { SceneMode, WardBed, WardRoom } from '@/modules/ward-map/types'

const props = defineProps<{
  /** **完整快照**的床位：过滤只隐藏网格，不重排几何（避免筛选时建筑跳变） */
  beds: WardBed[]
  rooms: WardRoom[]
  /** 当前筛选后可见的床位 id */
  visibleIds: number[]
  selectedId: number | null
  viewMode: SceneMode
  focusFloor: string
  /** 由外层传入的当前主题（影响曝光） */
  dark?: boolean
  /** 沙盘 What-if 假设中临时停用的床位（灰色轮廓，不改变真实主状态色） */
  simulationUnavailableIds?: number[]
  /** 沙盘候选床位（青色轮廓） */
  simulationCandidateIds?: number[]
  /** 当前模拟方案命中的床位（金色轮廓） */
  simulationAssignedIds?: number[]
  /** 首个虚构申请得分最高的床位（更亮的金色） */
  simulationTopBedId?: number | null
}>()

const emit = defineEmits<{
  (e: 'hover', bed: WardBed | null, screen: { x: number; y: number }): void
  (e: 'select', bed: WardBed): void
  (e: 'unavailable'): void
}>()

const viewport = ref<HTMLDivElement | null>(null)
const pointer = new THREE.Vector2()
const raycaster = new THREE.Raycaster()

/* ------------------------------ 共享资源 ------------------------------ */
const boxGeometry = new THREE.BoxGeometry(1, 1, 1)
const sphereGeometry = new THREE.SphereGeometry(1, 18, 12)
const cylinderGeometry = new THREE.CylinderGeometry(1, 1, 1, 12)
const sharedGeometries = new Set<THREE.BufferGeometry>([
  boxGeometry,
  sphereGeometry,
  cylinderGeometry,
])

const baseMaterials: THREE.Material[] = []
const temporaryMaterials: THREE.Material[] = []
const temporaryTextures: THREE.Texture[] = []
const materials = new Map<string, THREE.MeshStandardMaterial>()

const pickTargets: THREE.Mesh[] = []

/**
 * 单床的悬停视觉状态。
 * `accent` / `surface` / `outlineMaterial` 都是**每床独立克隆**的材质：
 * 就地修改共享材质会把同状态的其他床一起染色。
 */
interface BedVisual {
  bed: WardBed
  /** 可见病床：只对它做浮起动画 */
  group: THREE.Group
  outline: THREE.Group
  floorKey: string
  /** 固定拾取体（挂在楼层 Group 上，不随床体浮起） */
  pick: THREE.Mesh
  accent: THREE.MeshStandardMaterial
  surface: THREE.MeshStandardMaterial
  outlineMaterial: THREE.MeshBasicMaterial
  restColor: THREE.Color
  hoverColor: THREE.Color
  surfaceRest: THREE.Color
  surfaceHover: THREE.Color
  lift: number
  velocity: number
  glow: number
}

/** 可被视线穿透并需要淡化的建筑构件（材质已逐对象克隆）。 */
interface OccludingSurface {
  mesh: THREE.Mesh
  material: THREE.MeshStandardMaterial
  original: number
  faded: number
  target: number
}

const selectable = new Map<number, BedVisual>()
const occludingSurfaces: OccludingSurface[] = []
const occlusionMeshes: THREE.Mesh[] = []
const occlusionRaycaster = new THREE.Raycaster()
const occlusionNdc = new THREE.Vector2()
const worldPosition = new THREE.Vector3()
let effectFrame = 0
let lastEffectTime = 0
const floors = new Map<string, THREE.Group>()
const shells: THREE.Group[] = []

let plan: HospitalPlan | undefined
let scene: THREE.Scene | undefined
let camera: THREE.OrthographicCamera | undefined
let renderer: THREE.WebGLRenderer | undefined
let controls: OrbitControls | undefined
let root: THREE.Group | undefined
let observer: ResizeObserver | undefined
let animationFrame = 0
let sceneTween = 0
let hoveredId: number | null = null
let pointerDown: { x: number; y: number } | null = null
let initialized = false
/** 切到后台时是否打断了一段未完的相机/楼层过渡，用于回前台补齐 */
let resumeTransitionAfterVisibility = false

/* ------------------------------ 材质与图元 ------------------------------ */

function material(
  key: string,
  color: string,
  params: Partial<THREE.MeshStandardMaterialParameters> = {},
) {
  let m = materials.get(key)
  if (!m) {
    m = new THREE.MeshStandardMaterial({ color, metalness: 0.04, roughness: 0.72, ...params })
    materials.set(key, m)
    baseMaterials.push(m)
  }
  return m
}

/** 医用装饰线（踢脚/腰线），让白墙不再是一整块空白板。 */
function medicalLine() {
  return material('medical-line', '#8fc0d4', { metalness: 0.12, roughness: 0.5 })
}

function cube(
  parent: THREE.Object3D,
  m: THREE.Material,
  x: number,
  y: number,
  z: number,
  w: number,
  h: number,
  d: number,
) {
  const mesh = new THREE.Mesh(boxGeometry, m)
  mesh.position.set(x, y, z)
  mesh.scale.set(w, h, d)
  mesh.castShadow = false
  mesh.receiveShadow = true
  parent.add(mesh)
  return mesh
}

/**
 * 建筑构件（楼板/地面/隔墙/框架/玻璃）。
 *
 * 与普通 `cube` 的区别：**克隆一份材质**并登记为可淡化对象。
 * 共享材质一旦被就地改不透明度，整层楼会一起变淡，因此必须逐对象实例化。
 * 克隆材质登记在 temporaryMaterials，场景重建时统一回收。
 */
function architecturalCube(
  parent: THREE.Object3D,
  base: THREE.MeshStandardMaterial,
  kind: OccluderKind,
  x: number,
  y: number,
  z: number,
  w: number,
  h: number,
  d: number,
) {
  const local = base.clone()
  temporaryMaterials.push(local)
  const mesh = cube(parent, local, x, y, z, w, h, d)
  const original = base.opacity
  occludingSurfaces.push({
    mesh,
    material: local,
    original,
    faded: fadedOccluderOpacity(kind, original),
    target: original,
  })
  occlusionMeshes.push(mesh)
  return mesh
}

function sphere(
  parent: THREE.Object3D,
  m: THREE.Material,
  x: number,
  y: number,
  z: number,
  w: number,
  h: number,
  d: number,
) {
  const mesh = new THREE.Mesh(sphereGeometry, m)
  mesh.scale.set(w, h, d)
  mesh.position.set(x, y, z)
  parent.add(mesh)
  return mesh
}

function cylinder(
  parent: THREE.Object3D,
  m: THREE.Material,
  x: number,
  y: number,
  z: number,
  w: number,
  h: number,
  d: number,
) {
  const mesh = new THREE.Mesh(cylinderGeometry, m)
  mesh.scale.set(w, h, d)
  mesh.position.set(x, y, z)
  parent.add(mesh)
  return mesh
}

/** 地面/墙面文字（病房牌、楼层号、医院标识）。用 Canvas 贴图，随主题反色。 */
function textLabel(
  parent: THREE.Object3D,
  text: string,
  x: number,
  y: number,
  z: number,
  w: number,
  h: number,
  kind: 'floor' | 'room' | 'brand' = 'room',
) {
  const canvas = document.createElement('canvas')
  canvas.width = 768
  canvas.height = 176
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, 768, 176)
  ctx.fillStyle = kind === 'brand' ? '#1b4a68' : kind === 'floor' ? '#1d5a80' : '#3f6a85'
  ctx.font = `${kind === 'brand' ? 800 : 700} ${kind === 'brand' ? 74 : kind === 'floor' ? 68 : 54}px "Microsoft YaHei",sans-serif`
  ctx.textBaseline = 'middle'
  ctx.fillText(text.slice(0, 24), 20, 92, 730)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  temporaryTextures.push(tex)
  const mat = new THREE.MeshBasicMaterial({
    map: tex,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
  })
  temporaryMaterials.push(mat)
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat)
  mesh.position.set(x, y, z)
  mesh.rotation.x = -Math.PI / 2
  parent.add(mesh)
}

/* -------------------------------- 病床 -------------------------------- */

/** 床垫上表面高度：患者与床品都以此为基准，避免悬空或穿模。 */
const MATTRESS_TOP = 0.655

function buildPatient(group: THREE.Group) {
  const skin = material('patient-skin', '#e0b79e')
  const scrubs = material('patient-scrubs', '#7fa6b8')
  const blanket = material('patient-blanket', '#bcd8e2')
  const hair = material('patient-hair', '#5b6169')
  const pillow = material('bed-pillow', '#ffffff')

  // 头枕在枕头上（枕面约 0.775），躯干/被褥贴合床垫面
  sphere(group, hair, 0, 0.905, -0.82, 0.2, 0.062, 0.13)
  sphere(group, skin, 0, 0.885, -0.7, 0.21, 0.145, 0.25)
  // 上身（病号服）
  cube(group, scrubs, 0, MATTRESS_TOP + 0.085, -0.16, 0.6, 0.17, 0.8)
  // 双臂自然垂放于身侧，贴近床垫
  sphere(group, skin, -0.375, MATTRESS_TOP + 0.075, -0.18, 0.115, 0.085, 0.4)
  sphere(group, skin, 0.375, MATTRESS_TOP + 0.075, -0.18, 0.115, 0.085, 0.4)
  // 被褥：盖住躯干以下，脚端略微翻折
  cube(group, blanket, 0, MATTRESS_TOP + 0.115, 0.6, 1.1, 0.23, 0.9)
  cube(group, blanket, 0, MATTRESS_TOP + 0.05, 1.04, 0.96, 0.1, 0.22)
  void pillow
}

function buildBed(
  floorGroup: THREE.Group,
  bed: WardBed,
  x: number,
  z: number,
  assignedFloor: string,
  orientation = 0,
) {
  const bedGroup = new THREE.Group()
  bedGroup.position.set(x, 0, z)
  // 参数化布局下南北病房镜像排布：南侧整房旋转 π，使床头一律朝外侧墙体。
  // 床位长轴沿 Z，绕 Y 旋转 π 后包围盒不变，因此固定拾取体无需跟着旋转。
  bedGroup.rotation.y = orientation
  floorGroup.add(bedGroup)

  const metal = material('bed-metal', '#b3c1cd', { metalness: 0.62, roughness: 0.3 })
  const enamel = material('bed-enamel', '#f7fafb', { metalness: 0.14, roughness: 0.36 })
  const padding = material('bed-padding', '#e6eff4', { roughness: 0.95 })
  const pillow = material('bed-pillow', '#ffffff')
  const rubber = material('bed-wheel', '#3f5568', { roughness: 0.9 })
  const status = material(
    'state-' + bed.status,
    sceneBedPalette[bed.status].base,
    { metalness: 0.1, roughness: 0.42, emissive: new THREE.Color(statusMeta[bed.status].hex).multiplyScalar(0.18) },
  )
  const glass = material('bed-pick', '#ffffff', { transparent: true, opacity: 0, depthWrite: false })

  // 底盘 + 四条短腿 + 脚轮
  cube(bedGroup, metal, 0, 0.26, 0, 1.34, 0.11, 2.46)
  for (const dx of [-0.56, 0.56]) {
    for (const dz of [-0.95, 0.95]) {
      cube(bedGroup, metal, dx, 0.15, dz, 0.07, 0.24, 0.09)
      cylinder(bedGroup, rubber, dx, 0.055, dz, 0.1, 0.075, 0.1)
    }
  }
  // 床体与床垫（床垫单独克隆，才能按床做悬停色过渡）
  cube(bedGroup, enamel, 0, 0.47, 0, 1.37, 0.17, 2.4)
  const surface = padding.clone()
  surface.color.set(sceneBedPalette[bed.status].surfaceBase)
  temporaryMaterials.push(surface)
  cube(bedGroup, surface, 0, 0.585, 0, 1.24, 0.14, 2.22)
  // 床头板（高）/ 床尾板（矮）
  cube(bedGroup, enamel, 0, 0.78, -1.185, 1.38, 0.84, 0.09)
  cube(bedGroup, enamel, 0, 0.55, 1.185, 1.38, 0.36, 0.1)
  cube(bedGroup, medicalLine(), 0, 0.5, -1.238, 1.2, 0.05, 0.02)
  // 护栏
  for (const dx of [-0.67, 0.67]) {
    for (const dz of [-0.74, 0.74]) cube(bedGroup, metal, dx, 0.74, dz, 0.05, 0.42, 0.05)
    cube(bedGroup, metal, dx, 0.94, 0, 0.055, 0.045, 1.5)
    cube(bedGroup, metal, dx, 0.79, 0, 0.04, 0.3, 1.42)
  }
  // 枕头（患者头部落点）
  sphere(bedGroup, pillow, 0, 0.7, -0.87, 0.5, 0.15, 0.26)

  // 状态只体现在床尾灯带与床下指示条上，而不是给整张床刷色。
  // 状态材质同样逐床克隆：直接改共享材质会让所有同状态床一起变色。
  const accent = status.clone()
  temporaryMaterials.push(accent)
  cube(bedGroup, accent, 0, 0.79, 1.245, 0.66, 0.1, 0.05)
  cube(bedGroup, accent, 0, 0.17, 1.12, 1.12, 0.055, 0.07)
  // 床头柜
  cube(bedGroup, enamel, 1.04, 0.33, -0.83, 0.5, 0.64, 0.48)
  cube(bedGroup, metal, 1.04, 0.57, -0.585, 0.32, 0.025, 0.03)

  if (isConfirmedOccupant(bed)) buildPatient(bedGroup)
  else if (bed.status === 'RESERVED') {
    cube(bedGroup, material('reservation-mark', '#9cbff2', { transparent: true, opacity: 0.6 }), 0, 0.79, 0.22, 0.5, 0.06, 0.44)
  } else if (bed.status === 'CLEANING') {
    cube(bedGroup, material('cleaning-mark', '#c3afea'), 0, 0.78, 0.16, 0.42, 0.07, 0.44)
  }

  // 床体投影到地面（玻璃与状态灯不投影）
  for (const child of bedGroup.children) {
    if (child instanceof THREE.Mesh) child.castShadow = true
  }

  // 独立拾取体积：与透明玻璃墙完全解耦，射线不会先打到建筑玻璃。
  // **挂在楼层 Group 而不是床体上** —— 床体浮起时命中区域必须留在原地，
  // 否则光标下的命中区跟着床往上跑，会产生持续的 Hover 抖动。
  const pick = cube(floorGroup, glass, x, 0.65, z, 1.88, 1.4, 2.82)
  pick.userData.bedId = bed.id
  pick.castShadow = false
  pickTargets.push(pick)

  // 悬停/选中描边（贴地灯带，不遮挡床体）
  const outline = new THREE.Group()
  bedGroup.add(outline)
  const outlineMaterial = new THREE.MeshBasicMaterial({
    color: sceneBedPalette[bed.status].outline,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    toneMapped: false,
  })
  temporaryMaterials.push(outlineMaterial)
  const highlight = outlineMaterial
  cube(outline, highlight, 0, 0.03, -1.36, 1.78, 0.04, 0.09)
  cube(outline, highlight, 0, 0.03, 1.36, 1.78, 0.04, 0.09)
  cube(outline, highlight, -0.86, 0.03, 0, 0.09, 0.04, 2.8)
  cube(outline, highlight, 0.86, 0.03, 0, 0.09, 0.04, 2.8)
  outline.visible = false

  selectable.set(bed.id, {
    bed,
    group: bedGroup,
    outline,
    pick,
    floorKey: assignedFloor,
    accent,
    outlineMaterial,
    surface,
    restColor: new THREE.Color(sceneBedPalette[bed.status].base),
    hoverColor: new THREE.Color(sceneBedPalette[bed.status].hover),
    // 交付包在此处漏传 surfaceRest/surfaceHover，动画循环会读到 undefined 并抛错，
    // 这里补齐（BedVisual 接口本来就声明了这两个字段）。
    surfaceRest: new THREE.Color(sceneBedPalette[bed.status].surfaceBase),
    surfaceHover: new THREE.Color(sceneBedPalette[bed.status].surfaceHover),
    lift: 0,
    velocity: 0,
    glow: 0,
  })
}

/* -------------------------------- 楼层 -------------------------------- */

function buildFloor(f: SceneFloor) {
  if (!root) return
  const layer = new THREE.Group()
  layer.name = `hospital-floor-${f.key}`
  layer.position.set(f.x, f.index * FLOOR_HEIGHT, -f.index * 0.35)
  root.add(layer)
  floors.set(f.key, layer)

  const slab = material('slab', '#dbe4ea')
  const floorMat = material('floor', '#f5f9f9')
  const wall = material('partition', '#ddeaf0')
  const wallTop = material('partition-top', '#fafdfd')
  const glass = material('glass', '#b7d9ea', {
    transparent: true,
    opacity: 0.1,
    depthWrite: false,
    side: THREE.DoubleSide,
  })
  const steel = material('steel', '#8aabbf', { metalness: 0.42, roughness: 0.42 })
  const corridor = material('corridor', '#eaf3f7')

  // 结构层：楼板 + 面层 + 沿边梁
  architecturalCube(layer, slab, 'slab', f.width / 2, -0.24, f.depth / 2, f.width, 0.44, f.depth)
  architecturalCube(layer, floorMat, 'floor', f.width / 2, -0.004, f.depth / 2, f.width, 0.055, f.depth)
  // 中央交通轴：逐层共用同一走廊轴线与宽度（scene-layout 给出的 f.corridorZ/corridorWidth），
  // 这是「所有楼层建筑轴线一致」在几何上的落点。
  architecturalCube(
    layer,
    corridor,
    'floor',
    f.width / 2,
    0.026,
    f.corridorZ,
    f.width - 0.5,
    0.044,
    f.corridorWidth,
  )
  architecturalCube(layer, steel, 'frame', f.width / 2, -0.03, f.depth, f.width, 0.13, 0.08)

  // 玻璃幕墙只做后墙与两侧，正面完全剖开（否则挡住全部床位）
  architecturalCube(layer, glass, 'glass', f.width / 2, 1.95, 0.35, f.width, 3.8, 0.09)
  architecturalCube(layer, glass, 'glass', 0.2, 1.95, f.depth / 2, 0.08, 3.8, f.depth)
  architecturalCube(layer, glass, 'glass', f.width - 0.2, 1.95, f.depth / 2, 0.08, 3.8, f.depth)
  for (const x of [0, f.width])
    for (const z of [0, f.depth]) architecturalCube(layer, steel, 'frame', x, 1.95, z, 0.16, 3.85, 0.16)
  for (let x = 4; x < f.width - 1; x += 5)
    architecturalCube(layer, steel, 'frame', x, 1.93, 0.36, 0.05, 3.8, 0.07)

  for (const r of f.rooms) {
    // 病房是规则模块：三面隔墙 + 朝中央走廊的两段前墙，中间留出 2.4 单位门洞。
    // 北侧病房的「背面」在 -Z，南侧镜像到 +Z，因此门一律朝走廊、床品不被实墙挡住。
    const back = r.side === 'north' ? r.z : r.z + r.depth
    const front = r.side === 'north' ? r.z + r.depth : r.z
    const center = r.x + r.width / 2
    architecturalCube(layer, wall, 'wall', center, 0.72, back, r.width, 1.43, 0.14)
    architecturalCube(layer, wall, 'wall', r.x, 0.69, r.z + r.depth / 2, 0.13, 1.37, r.depth)
    architecturalCube(layer, wall, 'wall', r.x + r.width, 0.69, r.z + r.depth / 2, 0.13, 1.37, r.depth)
    architecturalCube(layer, wall, 'wall', r.x + 2.45, 0.68, front, 4.9, 1.35, 0.12)
    architecturalCube(layer, wall, 'wall', r.x + r.width - 2.45, 0.68, front, 4.9, 1.35, 0.12)
    architecturalCube(layer, wallTop, 'wall', center, 1.44, back, r.width, 0.075, 0.16)
    // 门洞地面装饰线 + 病房牌（贴地，位于房间中轴）
    architecturalCube(layer, medicalLine(), 'floor', center, 0.065, front, 0.6, 0.016, 0.18)
    textLabel(layer, `${r.room.code} · ${r.room.name}`, r.x + 3.0, 0.065, r.z + r.depth / 2, 5.0, 0.6)
  }

  for (const item of f.beds) buildBed(layer, item.bed, item.x, item.z, f.key, item.orientation)

  // 楼层侧标（悬浮在楼板外侧，不占室内空间）
  const side = new THREE.Group()
  layer.add(side)
  cube(side, material('level-chip', '#eaf5fb'), -0.8, 0.42, 1.8, 0.18, 0.86, 3.4)
  textLabel(side, `${f.floor}F`, -0.68, 0.86, 1.6, 2.2, 0.8, 'floor')
}

/* ------------------------------ 医院外壳 ------------------------------ */

function buildHospitalShell() {
  if (!root || !plan) return
  for (const building of plan.buildings) {
    const shell = new THREE.Group()
    shell.position.x = building.x
    root.add(shell)
    shells.push(shell)

    const white = material('shell-white', '#f6fafd')
    const edge = material('shell-frame', '#a0bccb', { metalness: 0.3, roughness: 0.5 })
    const glass = material('shell-glass', '#9ecfe7', {
      transparent: true,
      opacity: 0.09,
      depthWrite: false,
      side: THREE.DoubleSide,
    })

    const height = building.floors.length * FLOOR_HEIGHT
    const w = building.width
    const d = building.depth

    // 剖切面：只在背面与两侧包玻璃，正面永不封闭
    architecturalCube(shell, glass, 'glass', w / 2, height / 2, 0.04, w, height, 0.06)
    architecturalCube(shell, glass, 'glass', 0.03, height / 2, d / 2, 0.06, height, d)
    architecturalCube(shell, glass, 'glass', w - 0.03, height / 2, d / 2, 0.06, height, d)

    // 角柱
    for (const x of [0, w])
      for (const z of [0, d]) architecturalCube(shell, edge, 'frame', x, height / 2, z, 0.22, height, 0.22)
    // 每层结构环梁
    for (let i = 0; i <= building.floors.length; i++) {
      const y = i * FLOOR_HEIGHT
      architecturalCube(shell, edge, 'frame', w / 2, y, 0.08, w, 0.18, 0.15)
      architecturalCube(shell, edge, 'frame', 0.06, y, d / 2, 0.15, 0.18, d)
      architecturalCube(shell, edge, 'frame', w - 0.06, y, d / 2, 0.15, 0.18, d)
    }
    // 顶部开敞檐口（只做周边梁，不封屋面，否则俯视时挡住上层床位）
    architecturalCube(shell, edge, 'frame', w / 2, height + 0.24, 0, w, 0.26, 0.28)
    architecturalCube(shell, edge, 'frame', w / 2, height + 0.24, d, w, 0.26, 0.28)
    architecturalCube(shell, edge, 'frame', 0, height + 0.24, d / 2, 0.28, 0.26, d)
    architecturalCube(shell, edge, 'frame', w, height + 0.24, d / 2, 0.28, 0.26, d)
    // 雨棚 + 医院标识
    cube(shell, white, w / 2, height + 0.6, 0.5, 4.4, 0.64, 0.8)
    cube(shell, material('medical-sign', '#3f9fab'), w / 2, height + 1.02, 0.51, 1.4, 0.09, 0.52)
    textLabel(shell, 'HOSPITAL', w / 2, height + 0.4, 1.08, 4.4, 0.68, 'brand')
  }
}

/* ------------------------------ 场景生命周期 ------------------------------ */

function markShadowsDirty() {
  if (renderer) renderer.shadowMap.needsUpdate = true
}

/* ------------------------- 悬停：遮挡探测与动画 ------------------------- */

function stopEffects() {
  if (effectFrame) cancelAnimationFrame(effectFrame)
  effectFrame = 0
  lastEffectTime = 0
}

/** 沿父链检查可见性：被筛选隐藏或所在楼层不可见的床不算命中。 */
function isVisibleObject(obj: THREE.Object3D) {
  let node: THREE.Object3D | null = obj
  while (node) {
    if (!node.visible) return false
    node = node.parent
  }
  return true
}

/**
 * 计算每块建筑构件的目标不透明度。
 *
 * 从被悬停床位的**屏幕投影位置**反向投射射线（而不是从相机目标点），
 * 只把「相机与该床位之间」被穿过的构件标记为需要淡化；正交视角下同样成立，
 * 且能正确命中床位上方楼层的楼板。没有构件挡住床位时，全部保持原外观。
 */
function updateOcclusionTargets() {
  let blocked = new Set<THREE.Mesh>()
  // 悬停优先，其次回退到「当前被选中的床」：点击选中后切换楼层/模式时，
  // 若只认 hoveredId，聚焦过渡期间会残留上一帧的半透明楼板与墙体。
  const targetId = hoveredId ?? props.selectedId
  const item = targetId === null ? null : selectable.get(targetId)
  if (item && camera && root && isVisibleObject(item.group)) {
    // 楼层补间进行中时，渲染矩阵可能仍是上一帧的；用陈旧变换做射线检测
    // 会让楼板/墙体的透明淡化滞后于床位本身。
    root.updateWorldMatrix(true, true)
    camera.updateMatrixWorld()
    const center = item.group.localToWorld(new THREE.Vector3(0, 0.74 - item.lift, 0))
    worldPosition.copy(center).project(camera)
    if (Math.abs(worldPosition.x) <= 1 && Math.abs(worldPosition.y) <= 1) {
      occlusionNdc.set(worldPosition.x, worldPosition.y)
      occlusionRaycaster.setFromCamera(occlusionNdc, camera)
      const length = center.clone().sub(occlusionRaycaster.ray.origin).dot(occlusionRaycaster.ray.direction)
      if (length > 0) {
        const hits = occlusionRaycaster.intersectObjects(occlusionMeshes, false)
        blocked = new Set(
          hits
            .filter((h) => h.distance < length - 0.09 && isVisibleObject(h.object))
            .map((h) => h.object as THREE.Mesh),
        )
      }
    }
  }
  for (const surface of occludingSurfaces)
    surface.target = blocked.has(surface.mesh) ? surface.faded : surface.original
}

function reduceMotion() {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * 单一 RAF 循环：床体弹簧升降 + 颜色/发光/框线/床垫过渡 + 遮挡透明度过渡。
 *
 * 「实时替换目标」而不是为每张床排队动画：hoveredId 改变时立刻改写目标值，
 * 当前值从上一次的位置连续趋近，因此快速划过 30~50 次也不会累积动画或颜色串床。
 * 所有值都被缓动夹在起止之间且收敛后吸附，稳定后自动停帧。
 */
function animateEffects(now: number) {
  effectFrame = 0
  const dt = lastEffectTime
    ? Math.min(0.045, Math.max(0.001, (now - lastEffectTime) / 1000))
    : 1 / 60
  lastEffectTime = now
  let active = false
  let lifting = false

  for (const [id, item] of selectable) {
    const hovering = id === hoveredId && isVisibleObject(item.group)
    const selected = id === props.selectedId
    // 沙盘叠加层只改描边色与透明度，**绝不覆盖床位主状态色**：
    // 真实业务状态（五态）永远优先，模拟结果只是叠加的轮廓提示。
    const assigned = props.simulationAssignedIds?.includes(id) ?? false
    const candidate = props.simulationCandidateIds?.includes(id) ?? false
    const top = props.simulationTopBedId === id
    const unavailable = props.simulationUnavailableIds?.includes(id) ?? false
    item.outlineMaterial.color.set(
      unavailable
        ? '#64748B'
        : assigned
          ? '#E5B348'
          : candidate
            ? '#0C9D9A'
            : sceneBedPalette[item.bed.status].outline,
    )
    const elevation = hovering ? HOVER_LIFT : 0
    // 轻微过阻尼弹簧：落下有回弹感，快速换目标时也不会瞬移
    const stiffness = 155
    const damping = 24
    item.velocity += (elevation - item.lift) * stiffness * dt
    item.velocity *= Math.exp(-damping * dt)
    item.lift += item.velocity * dt
    if (isNear(item.lift, elevation, 0.0015) && Math.abs(item.velocity) < 0.007) {
      item.lift = elevation
      item.velocity = 0
    }
    if (item.lift !== 0) lifting = true
    item.group.position.y = item.lift

    item.glow = easedApproach(item.glow, hovering ? 1 : 0, dt, 13)
    if (isNear(item.glow, hovering ? 1 : 0, 0.003)) item.glow = hovering ? 1 : 0
    item.accent.color.copy(item.restColor).lerp(item.hoverColor, item.glow)
    item.surface.color.copy(item.surfaceRest).lerp(item.surfaceHover, item.glow * 0.7)
    item.accent.emissive.copy(item.hoverColor).multiplyScalar(item.glow * 0.16)
    item.accent.emissiveIntensity = 0.7

    // 悬停最亮 > 模拟命中 > 选中 / 模拟首选 > 临时停用 > 普通候选
    const outlineAlpha = hovering
      ? 0.92
      : selected
        ? 0.75
        : unavailable
          ? 0.64
          : assigned
            ? 0.82
            : top
              ? 0.75
              : candidate
                ? 0.5
                : 0
    item.outlineMaterial.opacity = easedApproach(item.outlineMaterial.opacity, outlineAlpha, dt, 13)
    if (isNear(item.outlineMaterial.opacity, outlineAlpha, 0.004))
      item.outlineMaterial.opacity = outlineAlpha
    item.outline.visible = item.outlineMaterial.opacity > 0.009

    if (
      item.lift !== elevation ||
      Math.abs(item.velocity) > 0.007 ||
      item.glow !== (hovering ? 1 : 0) ||
      item.outlineMaterial.opacity !== outlineAlpha
    )
      active = true
  }

  for (const surface of occludingSurfaces) {
    const mat = surface.material
    mat.opacity = easedApproach(mat.opacity, surface.target, dt, 10)
    if (isNear(mat.opacity, surface.target, 0.004)) mat.opacity = surface.target
    // 淡出期间需要 transparent；恢复不透明后把 depthWrite 打开，
    // 否则会残留错误的深度排序，看起来像「透明没恢复」。
    const transparent = mat.opacity < 0.995 || surface.original < 0.995
    if (mat.transparent !== transparent || mat.depthWrite !== !transparent) {
      mat.transparent = transparent
      mat.depthWrite = !transparent
      mat.needsUpdate = true
    }
    if (mat.opacity !== surface.target) active = true
  }

  // 床体浮起会改变投影，阴影贴图是手动重算的，这里只在有床在运动时刷新
  if (lifting) markShadowsDirty()
  render()
  if (active) effectFrame = requestAnimationFrame(animateEffects)
  else lastEffectTime = 0
}

/** 减弱动效路径：直接落到目标状态，不做动画但保留状态与遮挡语义。 */
function animateEffectsReduced() {
  for (const [id, item] of selectable) {
    const on = id === hoveredId && isVisibleObject(item.group)
    const assigned = props.simulationAssignedIds?.includes(id) ?? false
    const candidate = props.simulationCandidateIds?.includes(id) ?? false
    const top = props.simulationTopBedId === id
    const unavailable = props.simulationUnavailableIds?.includes(id) ?? false
    item.outlineMaterial.color.set(
      unavailable
        ? '#64748B'
        : assigned
          ? '#E5B348'
          : candidate
            ? '#0C9D9A'
            : sceneBedPalette[item.bed.status].outline,
    )
    item.lift = on ? HOVER_LIFT : 0
    item.velocity = 0
    item.group.position.y = item.lift
    item.glow = on ? 1 : 0
    item.accent.color.copy(on ? item.hoverColor : item.restColor)
    item.surface.color.copy(item.surfaceRest).lerp(item.surfaceHover, on ? 0.7 : 0)
    item.accent.emissive.copy(item.hoverColor).multiplyScalar(on ? 0.16 : 0)
    // [LOCAL HARDENING 2026-10-15] 透明度优先级必须与 animateEffects 逐项一致：
    // 悬停 > 选中 > 沙盘临时停用 > 沙盘命中 > 沙盘首选 > 沙盘候选 > 不显示。
    // 交付版本这里漏了 unavailable 与 top —— 在「减弱动效」路径下，一张仅被
    // What-if 临时停用（且不在候选集）的床会拿到灰色色值却 alpha=0，
    // 于是 3D 上灰色轮廓整块消失，与交付说明里「保留状态语义」的要求不符。
    const alpha = on
      ? 0.92
      : id === props.selectedId
        ? 0.75
        : unavailable
          ? 0.64
          : assigned
            ? 0.82
            : top
              ? 0.75
              : candidate
                ? 0.5
                : 0
    item.outlineMaterial.opacity = alpha
    item.outline.visible = alpha > 0
  }
  for (const s of occludingSurfaces) {
    s.material.opacity = s.target
    const transparent = s.target < 0.995 || s.original < 0.995
    s.material.transparent = transparent
    s.material.depthWrite = !transparent
    s.material.needsUpdate = true
  }
  render()
}

function startEffects() {
  if (!initialized) return
  // 标签页不可见时不排帧：后台 RAF 会被浏览器节流，排了只会积压，
  // 回到前台还要先把过期动画追一帧。真正的重算交给 visibilitychange。
  if (document.hidden) {
    stopEffects()
    return
  }
  if (reduceMotion()) {
    stopEffects()
    animateEffectsReduced()
    return
  }
  if (!effectFrame) {
    lastEffectTime = 0
    effectFrame = requestAnimationFrame(animateEffects)
  }
}

function clearScene() {
  // 场景重建前先停掉效果循环并清空悬停态：否则旧 selectable 的 RAF 会
  // 继续写已 dispose 的材质，触发 WebGL 报错。
  stopEffects()
  if (hoveredId !== null) {
    emit('hover', null, { x: 0, y: 0 })
    hoveredId = null
  }
  if (root && scene) {
    root.traverse((obj) => {
      if (obj instanceof THREE.Mesh && !sharedGeometries.has(obj.geometry)) obj.geometry.dispose()
    })
    scene.remove(root)
  }
  temporaryTextures.splice(0).forEach((t) => t.dispose())
  temporaryMaterials.splice(0).forEach((m) => m.dispose())
  root = undefined
  pickTargets.length = 0
  selectable.clear()
  floors.clear()
  shells.length = 0
  occludingSurfaces.length = 0
  occlusionMeshes.length = 0
}

function rebuild() {
  if (!scene || !camera) return
  clearScene()
  root = new THREE.Group()
  scene.add(root)
  plan = createHospitalPlan(props.rooms, props.beds)
  for (const f of plan.floors) buildFloor(f)
  buildHospitalShell()
  updateVisibility()
  updateHighlights()
  applyMode(false)
  markShadowsDirty()
  render()
}

function updateVisibility() {
  const ids = new Set(props.visibleIds)
  for (const [id, item] of selectable) {
    item.group.visible = ids.has(id)
    // 拾取体挂在楼层 Group 上（不随浮起动画移动），因此必须**单独**跟随筛选隐藏，
    // 否则被筛掉的床仍能被射线命中、点开抽屉。
    item.pick.visible = ids.has(id)
  }
  // 被筛掉的床不可能继续悬停：清空悬停态，否则会残留浮起与遮挡淡化
  if (hoveredId !== null && !ids.has(hoveredId)) {
    hoveredId = null
    emit('hover', null, { x: 0, y: 0 })
  }
  updateOcclusionTargets()
  startEffects()
}

/** 高亮状态由效果循环按目标值缓动推进，这里只负责驱动它。 */
function updateHighlights() {
  updateOcclusionTargets()
  startEffects()
}

function render() {
  if (renderer && scene && camera) renderer.render(scene, camera)
}

/* --------------------------------- 镜头 --------------------------------- */

function sceneBounds(targetFloors: SceneFloor[]) {
  if (!targetFloors.length) return { minX: 0, maxX: 25, minZ: 0, maxZ: 25, minY: 0, maxY: 15 }
  return {
    minX: Math.min(...targetFloors.map((f) => f.x)),
    maxX: Math.max(...targetFloors.map((f) => f.x + f.width)),
    minZ: 0,
    maxZ: Math.max(...targetFloors.map((f) => f.depth)),
    minY: Math.min(...targetFloors.map((f) => f.index * FLOOR_HEIGHT)),
    maxY: Math.max(...targetFloors.map((f) => f.index * FLOOR_HEIGHT + FLOOR_HEIGHT)),
  }
}

function targetCamera(targetFloors: SceneFloor[], expanded = false) {
  const b = sceneBounds(targetFloors)
  const cx = (b.minX + b.maxX) / 2
  const cy = (b.minY + b.maxY) / 2
  const cz = (b.minZ + b.maxZ) / 2
  const dx = b.maxX - b.minX
  const dz = b.maxZ - b.minZ
  const dy = b.maxY - b.minY + (expanded ? Math.max(0, targetFloors.length - 1) * 2.2 : 0)
  const span = Math.max(22, dx + dz * 0.58 + 7, dy * 1.25 + dz * 0.45 + 8)
  const aspect = Math.max(0.75, (viewport.value?.clientWidth || 1200) / (viewport.value?.clientHeight || 650))
  // 正交相机：视口固定 30 单位高，按包围盒跨度求缩放，窄屏自动后退
  const zoom = Math.max(0.26, Math.min(2.2, (30 * Math.min(1, aspect * 0.96)) / span) * 1.55)
  const target = new THREE.Vector3(cx, cy, cz)
  return { target, position: target.clone().add(new THREE.Vector3(span * 0.74, span * 0.62, span * 0.85)), zoom }
}

function animateTo(target: THREE.Vector3, position: THREE.Vector3, zoom: number, animated = true) {
  if (!camera || !controls) return
  if (animationFrame) cancelAnimationFrame(animationFrame)
  const look0 = controls.target.clone()
  const pos0 = camera.position.clone()
  const zoom0 = camera.zoom
  const duration = animated && !window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 580 : 0
  if (!duration) {
    controls.target.copy(target)
    camera.position.copy(position)
    camera.zoom = zoom
    camera.updateProjectionMatrix()
    controls.update()
    render()
    return
  }
  const started = performance.now()
  const tick = (time: number) => {
    if (!camera || !controls) return
    const progress = Math.min(1, (time - started) / duration)
    const t = 1 - Math.pow(1 - progress, 3)
    controls.target.copy(look0).lerp(target, t)
    camera.position.copy(pos0).lerp(position, t)
    camera.zoom = zoom0 + (zoom - zoom0) * t
    camera.updateProjectionMatrix()
    controls.update()
    render()
    if (progress < 1) animationFrame = requestAnimationFrame(tick)
    else animationFrame = 0
  }
  animationFrame = requestAnimationFrame(tick)
}

function resetCamera() {
  if (!plan) return
  applyMode(true)
}

/** 飞向指定床位（点击抽屉「定位」与列表点选时使用）。 */
function focusBed(id: number) {
  if (!plan) return
  const loc = plan.bedLocations[id]
  const floor = plan.floors.find((f) => f.key === plan?.bedFloors[id])
  const group = floor ? floors.get(floor.key) : null
  if (!loc || !floor || !group) return
  const target = new THREE.Vector3(loc.x, group.position.y + 0.8, loc.z)
  const delta = new THREE.Vector3(12.5, 12.8, 15.5)
  animateTo(target, target.clone().add(delta), 1.42)
}

function applyMode(animated = true) {
  if (!plan) return
  if (sceneTween) cancelAnimationFrame(sceneTween)
  const targets = new Map<string, number>()
  for (const f of plan.floors) {
    const visible = props.viewMode !== 'focus' || f.key === props.focusFloor || (!props.focusFloor && f === plan.floors[0])
    const group = floors.get(f.key)
    if (group) group.visible = visible
    targets.set(f.key, f.index * (FLOOR_HEIGHT + (props.viewMode === 'exploded' ? 2.4 : 0)))
  }
  shells.forEach((s) => {
    s.visible = props.viewMode === 'building'
  })
  const originals = new Map([...floors].map(([k, g]) => [k, g.position.y]))
  const start = performance.now()
  const duration = animated && !window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 520 : 0
  const frame = (now: number) => {
    const pct = duration ? Math.min(1, (now - start) / duration) : 1
    const e = 1 - (1 - pct) ** 3
    for (const [key, group] of floors) {
      const a = originals.get(key) || 0
      const b = targets.get(key) || 0
      group.position.y = a + (b - a) * e
    }
    // 楼层在移动，遮挡关系每帧都在变；被选中的床即使当前没有悬停，
    // 也要跟着重算，否则聚焦过渡期间会残留过期的半透明楼板/墙体。
    if (hoveredId !== null || props.selectedId !== null) {
      updateOcclusionTargets()
      startEffects()
    }
    render()
    if (pct < 1) {
      sceneTween = requestAnimationFrame(frame)
    } else {
      sceneTween = 0
      markShadowsDirty()
    }
  }
  frame(start)

  const active =
    props.viewMode === 'focus' ? plan.floors.filter((f) => f.key === props.focusFloor).slice(0, 1) : plan.floors
  const framing = targetCamera(active.length ? active : plan.floors, props.viewMode === 'exploded')
  if (props.viewMode === 'focus' && active.length) {
    framing.target.y = active[0].index * FLOOR_HEIGHT + 1.5
    framing.position = framing.target.clone().add(new THREE.Vector3(24, 23, 28))
    framing.zoom = Math.min(1.7, framing.zoom * 1.4)
  }
  animateTo(framing.target, framing.position, framing.zoom, animated)
}

/* --------------------------------- 拾取 --------------------------------- */

/** 相机平移/缩放会改变遮挡关系，因此重算淡化目标而不是沿用上一帧结果。 */
function onCameraChange() {
  if (hoveredId !== null) {
    updateOcclusionTargets()
    startEffects()
  }
  render()
}

function isPickVisible(mesh: THREE.Object3D) {
  return isVisibleObject(mesh)
}

function pick(e: PointerEvent | MouseEvent): WardBed | null {
  if (!camera || !renderer) return null
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.set(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1,
  )
  raycaster.setFromCamera(pointer, camera)
  for (const hit of raycaster.intersectObjects(pickTargets, false)) {
    if (!isPickVisible(hit.object)) continue
    const item = selectable.get(Number(hit.object.userData.bedId))
    if (item) return item.bed
  }
  return null
}

function pointerMove(e: PointerEvent) {
  const bed = pick(e)
  const next = bed?.id ?? null
  if (next !== hoveredId) {
    hoveredId = next
    updateOcclusionTargets()
    updateHighlights()
    render()
  }
  const bounds = viewport.value?.getBoundingClientRect()
  emit('hover', bed, { x: e.clientX - (bounds?.left || 0), y: e.clientY - (bounds?.top || 0) })
  if (renderer) renderer.domElement.style.cursor = bed ? 'pointer' : 'grab'
}

function pointerLeave() {
  hoveredId = null
  updateOcclusionTargets()
  updateHighlights()
  emit('hover', null, { x: 0, y: 0 })
  render()
}

function pointerStart(e: PointerEvent) {
  pointerDown = { x: e.clientX, y: e.clientY }
}

function click(e: MouseEvent) {
  if (pointerDown && Math.hypot(e.clientX - pointerDown.x, e.clientY - pointerDown.y) > 6) return
  const bed = pick(e)
  if (bed) emit('select', bed)
}

function resize() {
  if (!camera || !renderer || !viewport.value) return
  const w = Math.max(1, viewport.value.clientWidth)
  const h = Math.max(1, viewport.value.clientHeight)
  renderer.setSize(w, h, false)
  const aspect = w / h
  camera.left = -15 * aspect
  camera.right = 15 * aspect
  camera.top = 15
  camera.bottom = -15
  camera.updateProjectionMatrix()
  render()
}

function exposure() {
  return props.dark ? 0.86 : 1
}

function initialize() {
  try {
    if (!viewport.value) return
    scene = new THREE.Scene()
    // 透明画布：底色交给 CSS 令牌渐变，明暗主题自动跟随
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = exposure()
    renderer.shadowMap.enabled = true
    // three 0.186 起 PCFSoftShadowMap 已废弃（运行时会 warning 并回退 PCFShadowMap），
    // 显式使用 PCFShadowMap 以保证 Console 干净。
    renderer.shadowMap.type = THREE.PCFShadowMap
    // 场景静止，阴影只在几何/楼层变化时重算
    renderer.shadowMap.autoUpdate = false
    renderer.domElement.setAttribute(
      'aria-label',
      '透明医院多楼层剖面，可用鼠标点选床位；下方提供键盘可达的床位列表',
    )
    viewport.value.appendChild(renderer.domElement)

    camera = new THREE.OrthographicCamera(-20, 20, 15, -15, 0.1, 700)
    camera.position.set(28, 30, 34)
    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableRotate = false
    controls.enableDamping = false
    controls.screenSpacePanning = true
    controls.minZoom = 0.26
    controls.maxZoom = 4.5
    controls.addEventListener('change', onCameraChange)

    scene.add(new THREE.HemisphereLight(0xf0f7ff, 0xa9b8c6, 1.5))
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.5)
    keyLight.position.set(20, 38, 26)
    keyLight.castShadow = true
    keyLight.shadow.mapSize.set(2048, 2048)
    keyLight.shadow.bias = -0.0012
    keyLight.shadow.normalBias = 0.03
    const cam = keyLight.shadow.camera
    cam.left = -70
    cam.right = 70
    cam.top = 70
    cam.bottom = -70
    cam.near = 1
    cam.far = 160
    cam.updateProjectionMatrix()
    scene.add(keyLight)
    scene.add(keyLight.target)
    const fill = new THREE.DirectionalLight(0xa9d9e3, 0.5)
    fill.position.set(-14, 18, -10)
    scene.add(fill)

    renderer.domElement.addEventListener('pointermove', pointerMove)
    renderer.domElement.addEventListener('pointerleave', pointerLeave)
    renderer.domElement.addEventListener('pointerdown', pointerStart)
    renderer.domElement.addEventListener('click', click)
    observer = new ResizeObserver(resize)
    observer.observe(viewport.value)
    document.addEventListener('visibilitychange', onDocumentVisibility)
    initialized = true
    rebuild()
    resize()
  } catch (e) {
    console.warn('Ward map WebGL unavailable', e)
    destroy()
    emit('unavailable')
  }
}

/**
 * 标签页可见性变化。
 *
 * 隐藏时只停「效果」帧是不够的：相机补间（animationFrame）与楼层补间
 * （sceneTween）同样在排帧，后台节流会让它们卡在半途。这里把三类帧一起取消，
 * 并记下是否打断了一段过渡；回到前台先把楼层过渡一次性补到一致状态，
 * 再恢复选中床位的聚焦与悬停遮挡，避免出现「半层楼」的中间态。
 */
function onDocumentVisibility() {
  if (document.hidden) {
    resumeTransitionAfterVisibility = Boolean(animationFrame || sceneTween)
    if (animationFrame) cancelAnimationFrame(animationFrame)
    animationFrame = 0
    if (sceneTween) cancelAnimationFrame(sceneTween)
    sceneTween = 0
    stopEffects()
  } else if (initialized) {
    if (resumeTransitionAfterVisibility) {
      resumeTransitionAfterVisibility = false
      applyMode(false)
      if (props.selectedId !== null && selectable.has(props.selectedId)) focusBed(props.selectedId)
    }
    updateOcclusionTargets()
    startEffects()
    render()
  }
}

function destroy() {
  document.removeEventListener('visibilitychange', onDocumentVisibility)
  if (animationFrame) cancelAnimationFrame(animationFrame)
  if (sceneTween) cancelAnimationFrame(sceneTween)
  stopEffects()
  observer?.disconnect()
  observer = undefined
  if (renderer) {
    renderer.domElement.removeEventListener('pointermove', pointerMove)
    renderer.domElement.removeEventListener('pointerleave', pointerLeave)
    renderer.domElement.removeEventListener('pointerdown', pointerStart)
    renderer.domElement.removeEventListener('click', click)
  }
  controls?.removeEventListener('change', onCameraChange)
  controls?.dispose()
  controls = undefined
  clearScene()
  for (const m of baseMaterials) m.dispose()
  baseMaterials.length = 0
  materials.clear()
  for (const g of sharedGeometries) g.dispose()
  renderer?.dispose()
  renderer?.domElement.remove()
  renderer = undefined
  camera = undefined
  scene = undefined
  initialized = false
  resumeTransitionAfterVisibility = false
}

onMounted(initialize)
onBeforeUnmount(destroy)

watch(
  () => [props.beds, props.rooms],
  () => {
    if (initialized) rebuild()
  },
)
watch(
  () => props.visibleIds,
  () => {
    updateVisibility()
    markShadowsDirty()
    render()
  },
)
watch(
  () => [props.viewMode, props.focusFloor],
  () => {
    // 切换观察模式前先解除悬停：楼层可见性与位置都要变，
    // 留着旧悬停会短暂点亮一张已经不在画面里的床。
    if (initialized) {
      pointerLeave()
      applyMode()
    }
  },
)
watch(
  () => props.selectedId,
  (id) => {
    updateHighlights()
    if (id != null) focusBed(id)
    else render()
  },
)
// 沙盘叠加层变化（候选/命中/假设停用）：只重算描边与遮挡，不重建场景
watch(
  () => [
    props.simulationCandidateIds,
    props.simulationAssignedIds,
    props.simulationUnavailableIds,
    props.simulationTopBedId,
  ],
  () => {
    updateHighlights()
    render()
  },
)
watch(
  () => props.dark,
  () => {
    if (renderer) {
      renderer.toneMappingExposure = exposure()
      render()
    }
  },
)

defineExpose({ resetCamera, focusBed, floorKeyOf: (id: number) => (plan ? plan.bedFloors[id] : undefined) })
</script>

<template>
  <div
    ref="viewport"
    class="ward-scene-canvas"
    role="img"
    aria-label="三维透明医院剖面：模拟建筑位置与真实业务床位状态"
  ></div>
</template>