"""敏感信息脱敏工具。

原型系统只使用虚构患者数据；即便如此，姓名 / 手机号 / 身份证号 / 联系地址
在默认视图下一律脱敏输出，管理员显式请求 reveal=true 时才返回原文，
且该行为会被写入审计日志。
"""

from __future__ import annotations

MASK_CHAR = "*"


def mask_name(name: str | None) -> str | None:
    """张三 -> 张*；欧阳小明 -> 欧**明；单字姓名 -> *。"""
    if not name:
        return name
    name = name.strip()
    if len(name) == 0:
        return name
    if len(name) == 1:
        return MASK_CHAR
    if len(name) == 2:
        return name[0] + MASK_CHAR
    return name[0] + MASK_CHAR * (len(name) - 2) + name[-1]


def mask_phone(phone: str | None) -> str | None:
    """13812345678 -> 138****5678。"""
    if not phone:
        return phone
    digits = phone.strip()
    if len(digits) < 7:
        return MASK_CHAR * len(digits)
    return digits[:3] + MASK_CHAR * (len(digits) - 7) + digits[-4:]


def mask_id_card(id_card: str | None) -> str | None:
    """110101199003071234 -> 110101**********34。"""
    if not id_card:
        return id_card
    value = id_card.strip()
    if len(value) <= 6:
        return MASK_CHAR * len(value)
    return value[:6] + MASK_CHAR * (len(value) - 8) + value[-2:]


def mask_address(address: str | None) -> str | None:
    if not address:
        return address
    value = address.strip()
    if len(value) <= 6:
        return value[0] + MASK_CHAR * (len(value) - 1) if value else value
    return value[:6] + MASK_CHAR * min(len(value) - 6, 8)


def mask_medical_record_no(no: str | None) -> str | None:
    if not no:
        return no
    value = no.strip()
    if len(value) <= 4:
        return MASK_CHAR * len(value)
    return value[:2] + MASK_CHAR * (len(value) - 4) + value[-2:]
