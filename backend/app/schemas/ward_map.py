"""只读床位态势图：坐标仅用于教学模拟空间，不代表真实医院平面图。"""
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict

BedState = Literal['AVAILABLE', 'RESERVED', 'OCCUPIED', 'CLEANING', 'MAINTENANCE']

class Position(BaseModel):
    x: float
    z: float

class PatientSummary(BaseModel):
    masked_name: str
    priority: str | None = None
    allocation_status: Literal['RESERVED', 'ADMITTED']
    admission_request_id: int

class WardMapBed(BaseModel):
    id: int
    code: str
    status: BedState
    bed_type: str
    is_isolation: bool
    ward_id: int
    ward_code: str
    ward_name: str
    department_id: int
    department_name: str
    floor: int
    building: str
    simulated_position: Position
    scene_slot: int | None = None
    scene_rotation: int | None = None
    patient: PatientSummary | None = None
    # 数据异常不能被模拟人物模型掩盖
    state_warning: str | None = None

class WardMapRoom(BaseModel):
    ward_id: int
    code: str
    name: str
    department_id: int
    department_name: str
    building: str
    floor: int
    simulated_position: Position
    bed_count: int

class WardMapResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    layout_kind: Literal['SIMULATED_GRID_V1'] = 'SIMULATED_GRID_V1'
    data_source: Literal['BUSINESS_API'] = 'BUSINESS_API'
    generated_at: datetime
    rooms: list[WardMapRoom]
    beds: list[WardMapBed]
    counts: dict[str, int]
