/**
 * 合成演示数据：仅在用户显式点击「演示数据」时启用。
 *
 * 与真实数据严格区分：`data_source = 'SYNTHETIC_DEMO'`，
 * 演示模式不会用合成床位 ID 去读取真实床位流水，API 报错也不会自动回退到这里。
 *
 * V2 规格：**3 个模拟楼层 / 6 个病房 / 44 张床**（verify_v2_layout.cjs 会校验这三个数），
 * 状态按固定序列铺开，保证每层都能看到空闲/预占/入住/清洁/维护五种状态与躺卧患者。
 */

import type { BedState, WardBed, WardMapSnapshot, WardRoom } from './types'

export function demoSnapshot(): WardMapSnapshot {
  const rooms: WardRoom[] = []
  const beds: WardBed[] = []
  const colors: BedState[] = [
    'AVAILABLE',
    'AVAILABLE',
    'OCCUPIED',
    'AVAILABLE',
    'RESERVED',
    'AVAILABLE',
    'OCCUPIED',
    'CLEANING',
    'AVAILABLE',
    'MAINTENANCE',
    'RESERVED',
  ]
  for (let i = 0; i < 6; i++) {
    const wardId = i + 1
    const deptId = Math.floor(i / 2) + 1
    const floor = 1 + Math.floor(i / 2)
    const code = `${floor}0${(i % 2) + 1}`
    const departmentName = ['心内科', '神经内科', '普通外科'][deptId - 1]
    const x = (i % 2) * 12.5
    const z = (floor - 1) * 17
    rooms.push({
      ward_id: wardId,
      code,
      name: `${code} 病房`,
      department_id: deptId,
      department_name: departmentName,
      building: '模拟住院楼',
      floor,
      simulated_position: { x, z },
      bed_count: i < 2 ? 8 : 7,
    })
    for (let j = 0; j < (i < 2 ? 8 : 7); j++) {
      const status = colors[(i * 7 + j) % colors.length]
      const admitted = status === 'OCCUPIED'
      const reserved = status === 'RESERVED'
      beds.push({
        id: i * 10 + j + 1,
        code: `${code}-${String(j + 1).padStart(2, '0')}`,
        ward_id: wardId,
        ward_code: code,
        ward_name: `${code} 病房`,
        department_id: deptId,
        department_name: departmentName,
        building: '模拟住院楼',
        floor,
        // 模拟排布：每排 4 床，横向 2.35 间距、纵向 3.25 间距（仅用于可视化）。
        // z 必须继承房间基准 z（与后端 ward_map.simulated_positions 的
        // `base_z + 1.65 + 行*3.25` 口径一致）；否则 scene-layout 按楼层 minZ
        // 归一化后，2F/3F 床位会落到 z<0 的楼板外。
        simulated_position: {
          x: x + 1.15 + (j % 4) * 2.35,
          z: z + 1.65 + Math.floor(j / 4) * 3.25,
        },
        bed_type: 'NORMAL',
        is_isolation: false,
        status,
        patient:
          admitted || reserved
            ? {
                masked_name: '模*患者',
                priority: ['NORMAL', 'URGENT', 'SEVERE'][j % 3],
                allocation_status: admitted ? 'ADMITTED' : 'RESERVED',
                admission_request_id: 9000 + i * 10 + j,
              }
            : null,
        state_warning: null,
      })
    }
  }
  const counts: Record<BedState, number> = {
    AVAILABLE: 0,
    RESERVED: 0,
    OCCUPIED: 0,
    CLEANING: 0,
    MAINTENANCE: 0,
  }
  beds.forEach((b) => counts[b.status]++)
  return {
    layout_kind: 'SIMULATED_GRID_V1',
    data_source: 'SYNTHETIC_DEMO',
    generated_at: new Date().toISOString(),
    rooms,
    beds,
    counts,
  }
}