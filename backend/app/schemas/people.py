"""患者 / 医生模型。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PatientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    gender: str = Field(..., description="MALE / FEMALE")
    birth_date: date | None = None
    id_card: str | None = Field(None, max_length=32)
    phone: str | None = Field(None, max_length=32)
    address: str | None = Field(None, max_length=255)
    blood_type: str | None = Field(None, max_length=8)
    is_infectious: bool = False
    allergy: str | None = Field(None, max_length=255)
    note: str | None = Field(None, max_length=255)


class PatientCreate(PatientBase):
    medical_record_no: str | None = Field(None, max_length=32, description="留空则自动生成")


class PatientUpdate(BaseModel):
    name: str | None = Field(None, max_length=64)
    phone: str | None = Field(None, max_length=32)
    address: str | None = Field(None, max_length=255)
    is_infectious: bool | None = None
    allergy: str | None = Field(None, max_length=255)
    note: str | None = Field(None, max_length=255)


class PatientRead(ORMModel):
    id: int
    medical_record_no: str
    name: str
    gender: str
    gender_label: str | None = None
    birth_date: date | None = None
    id_card: str | None = None
    phone: str | None = None
    address: str | None = None
    blood_type: str | None = None
    is_infectious: bool = False
    allergy: str | None = None
    note: str | None = None
    masked: bool = True


class DoctorBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    department_id: int
    title: str | None = Field(None, max_length=32)
    phone: str | None = Field(None, max_length=32)
    is_active: bool = True


class DoctorCreate(DoctorBase):
    username: str | None = Field(
        None, max_length=64, description="可选：同时创建登录账号（角色 DOCTOR）"
    )
    password: str | None = Field(None, min_length=4, max_length=128)


class DoctorRead(ORMModel):
    id: int
    name: str
    department_id: int
    department_name: str | None = None
    title: str | None = None
    phone: str | None = None
    is_active: bool = True
    user_id: int | None = None
