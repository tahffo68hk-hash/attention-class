/**
 * Ward Map Hover Visual V3 —— **仅 3D 态势图场景使用**的配色与动画参数。
 *
 * 边界（重要）：
 * - 本模块**不改变后端五态**（AVAILABLE / RESERVED / OCCUPIED / CLEANING /
 *   MAINTENANCE），也不改变全系统统一状态色 `types.statusMeta`；
 *   床位管理页、列表徽标等仍用 `statusMeta`，此处只服务于 Three.js 场景与
 *   /ward-map 页面内的图例/统计/悬停卡，保证「3D 里看到的颜色」与
 *   「态势图页面里读到的颜色」一致。
 * - 红色系是「不能直接分配」的视觉分组（预占 / 已入住），黄色**只**表示
 *   空闲床的悬停提示色，不代表任何业务状态。
 * - 这里的动画参数同样只影响视觉层，不参与推荐评分与分配逻辑。
 *
 * 与交付包的差异（本地适配）：
 * - 类型导入改走 `@/modules/ward-map/types`（本仓库模块路径约定），
 *   但 `BedState` 仍来自该模块，因此配色键与后端五态严格对齐。
 */

/** 会被视线穿透、因而需要淡化的建筑构件类别。 */
export type OccluderKind = 'slab' | 'floor' | 'wall' | 'frame' | 'glass'

export interface SceneBedPalette {
  /** 静止时的状态灯/床下指示条颜色 */
  base: string
  /** 悬停时的颜色（预占与入住仍保持红系） */
  hover: string
  /** 贴地框线颜色 */
  outline: string
  /** 床垫基色 */
  surfaceBase: string
  /** 悬停时的床垫颜色 */
  surfaceHover: string
}

/**
 * 五态场景配色。
 * - AVAILABLE 绿 → 悬停转柔和黄（唯一会把颜色语义整体切换的状态）；
 * - RESERVED 柔和红 / OCCUPIED 深红，**两者悬停后仍是红系**，避免把
 *   「已占用」误读成「可用」；
 * - CLEANING 紫、MAINTENANCE 灰，保持与业务语义的既有区分。
 */
export const sceneBedPalette: Record<
  import('./types').BedState,
  SceneBedPalette
> = {
  AVAILABLE: {
    base: '#2EAD84',
    hover: '#FFD44D',
    outline: '#F3C94A',
    surfaceBase: '#E1ECF1',
    surfaceHover: '#FFF0BE',
  },
  RESERVED: {
    base: '#D77678',
    hover: '#F6A4A2',
    outline: '#EA8187',
    surfaceBase: '#F8DDDC',
    surfaceHover: '#F9C5C4',
  },
  OCCUPIED: {
    base: '#C45059',
    hover: '#F17B80',
    outline: '#E65B6A',
    surfaceBase: '#F1CCCF',
    surfaceHover: '#F2B1B7',
  },
  CLEANING: {
    base: '#9675D9',
    hover: '#B89AE7',
    outline: '#A987E7',
    surfaceBase: '#EDE6F7',
    surfaceHover: '#E3D5F5',
  },
  MAINTENANCE: {
    base: '#8793A3',
    hover: '#B1BCC8',
    outline: '#98A7B9',
    surfaceBase: '#E2E7EE',
    surfaceHover: '#D2DCE5',
  },
}

/**
 * 遮挡构件的淡化目标不透明度。
 *
 * 只淡化「相机与被悬停床位之间」被射线穿过的构件；这些下限保证楼层轮廓
 * 与空间关系始终可读，不会因为悬停而让整层楼消失。
 */
export function fadedOccluderOpacity(kind: OccluderKind, baseOpacity: number): number {
  const target: Record<OccluderKind, number> = {
    slab: 0.19,
    floor: 0.2,
    wall: 0.18,
    frame: 0.24,
    glass: 0.045,
  }
  return Math.min(baseOpacity, target[kind])
}

/**
 * 帧率无关的指数趋近：返回严格落在 from..to 之间的值，
 * 因此快速切换悬停目标时不会出现反向跳变或过冲。
 */
export function easedApproach(
  from: number,
  to: number,
  elapsedSeconds: number,
  speed = 11,
): number {
  return from + (to - from) * (1 - Math.exp(-speed * Math.max(0, elapsedSeconds)))
}

/** 收敛判定：到达目标后吸附，避免无穷小抖动持续占用 RAF。 */
export function isNear(a: number, b: number, epsilon = 0.003): boolean {
  return Math.abs(a - b) < epsilon
}

/** 悬停时床体沿局部 Y 抬升的视觉单位（拾取体不跟随，故不产生 Hover 抖动）。 */
export const HOVER_LIFT = 0.3