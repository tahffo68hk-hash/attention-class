"""3D administrator actions. Explicit confirmation; separate scene slot from clinical score coordinates."""
from pydantic import BaseModel,Field,ConfigDict
from typing import Literal
from decimal import Decimal

class ManagedBedCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm: Literal[True]
    code: str = Field(min_length=1,max_length=32)
    ward_id: int = Field(gt=0,strict=True)
    scene_slot: int = Field(ge=0,le=999,strict=True)
    rotation: Literal[0,90,180,270] = 0
    template_bed_id: int = Field(gt=0,strict=True)
    bed_type: Literal['NORMAL','ISOLATION','MONITOR']
    gender_limit: Literal['ANY','MALE','FEMALE'] = 'ANY'
    daily_rate: Decimal = Field(ge=0,le=100000)
    note: str|None = Field(None,max_length=255)

class ManagedBedAction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm: Literal[True]
    reason: str = Field(min_length=2,max_length=255)

class ManagedBedPose(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm: Literal[True]
    ward_id: int = Field(gt=0,strict=True)
    scene_slot: int = Field(ge=0,le=999,strict=True)
    rotation: Literal[0,90,180,270] = 0

class ManagedBedOut(BaseModel):
    id: int
    code: str
    ward_id: int
    scene_slot: int
    rotation: int
    retired: bool
    status: str
