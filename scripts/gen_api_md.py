"""从源码生成 API.md（路径 / 方法 / 用途 / 鉴权）。

为什么不手写：接口会变，手写表迟早与代码不一致。这里直接解析
`app/api/v1/*.py` 的 APIRouter 与装饰器，得到与运行时 OpenAPI 完全一致的
「方法 + 完整路径 + summary + 角色要求」。

用法（在 backend/ 目录下）：
    python ../scripts/gen_api_md.py            # 写到仓库根目录 API.md
    python ../scripts/gen_api_md.py --check    # 只比对，不一致则退出码 1
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
API_DIR = BACKEND / "app" / "api" / "v1"
OUT = Path(__file__).resolve().parents[1] / "API.md"

API_PREFIX = "/api/v1"

ROLE_LABEL = {
    "ADMIN": "管理员",
    "DOCTOR": "医生",
    "NURSE": "护士",
    "VIEWER": "只读",
}

METHOD_ORDER = {"get": 0, "post": 1, "put": 2, "patch": 3, "delete": 4}


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _dotted(node: ast.AST) -> str:
    """把 `UserRole.ADMIN` / `ALLOCATION_OPERATOR_ROLES` 还原成文本。"""
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return ""


def collect() -> list[dict]:
    items: list[dict] = []

    for path in sorted(API_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        # 模块级常量：ALLOCATION_OPERATOR_ROLES = (UserRole.NURSE, UserRole.ADMIN)
        role_sets: dict[str, list[str]] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Tuple, ast.List)):
                names = [n for n in (_dotted(e) for e in node.value.elts) if n]
                if names:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            role_sets[target.id] = names

        # router 变量 -> (prefix, tags)
        routers: dict[str, tuple[str, list[str]]] = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if not (isinstance(func, ast.Name) and func.id == "APIRouter"):
                continue
            prefix, tags = "", []
            for kw in node.value.keywords:
                if kw.arg == "prefix" and _const_str(kw.value):
                    prefix = _const_str(kw.value) or ""
                if kw.arg == "tags" and isinstance(kw.value, ast.List):
                    tags = [s for s in (_const_str(e) for e in kw.value.elts) if s]
            for target in node.targets:
                if isinstance(target, ast.Name):
                    routers[target.id] = (prefix, tags)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                method = dec.func.attr
                if method not in METHOD_ORDER:
                    continue
                owner = dec.func.value
                if not isinstance(owner, ast.Name) or owner.id not in routers:
                    continue
                route = _const_str(dec.args[0]) if dec.args else ""
                if route is None:
                    continue

                summary = ""
                roles: list[str] = []
                for kw in dec.keywords:
                    if kw.arg == "summary" and _const_str(kw.value):
                        summary = _const_str(kw.value) or ""
                    if kw.arg == "dependencies":
                        for sub in ast.walk(kw.value):
                            if isinstance(sub, ast.Call) and _dotted(sub.func).endswith("require_roles"):
                                for arg in sub.args:
                                    # require_roles(*ALLOCATION_OPERATOR_ROLES) 要拆包
                                    if isinstance(arg, ast.Starred):
                                        arg = arg.value
                                    name = _dotted(arg)
                                    if name.startswith("UserRole."):
                                        roles.append(name.split(".")[-1])
                                    elif name in role_sets:
                                        roles += [r.split(".")[-1] for r in role_sets[name]]

                # 处理函数是否注入 CurrentUser（用于判定必须先登录）
                needs_login = any(
                    _dotted(a.annotation).endswith("CurrentUser") or
                    (isinstance(a.annotation, ast.Name) and a.annotation.id == "CurrentUser")
                    for a in node.args.args
                    if a.annotation is not None
                )

                prefix, tags = routers[owner.id]
                items.append(
                    {
                        "method": method.upper(),
                        "path": f"{API_PREFIX}{prefix}{route}",
                        "summary": summary,
                        "tag": tags[0] if tags else "其他",
                        "roles": sorted(set(roles)),
                        "needs_login": needs_login or bool(roles),
                        "source": path.name,
                    }
                )

    # 去重（同一 endpoint 可能被 walk 到多次）
    seen: set[tuple[str, str]] = set()
    unique = []
    for it in items:
        key = (it["method"], it["path"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
    return unique


def auth_text(item: dict) -> str:
    roles = item["roles"]
    if roles:
        return "JWT + " + "/".join(ROLE_LABEL.get(r, r) for r in roles) if len(roles) == 1 else \
            "JWT + " + "、".join(ROLE_LABEL.get(r, r) for r in roles)
    if item["needs_login"]:
        return "JWT（任意已登录角色）"
    return "公开"


def render(items: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(it["tag"], []).append(it)

    total = len(items)
    lines: list[str] = []
    lines.append("# API 接口表\n")
    lines.append(
        "> 本文件由 `scripts/gen_api_md.py` 从 `backend/app/api/v1/*.py` 源码解析生成，"
        "与运行时 `/openapi.json` 一致；改动接口后请重新生成。\n"
    )
    lines.append(f"* 基础地址：`http://127.0.0.1:8000`，统一前缀 `{API_PREFIX}`")
    lines.append("* 在线文档：`/docs`（Swagger UI）、`/redoc`、`/openapi.json`")
    lines.append(f"* 端点总数：**{total}**（`{API_PREFIX}` 下），另有 `GET /`、`GET /health` 两个无前缀端点")
    lines.append("* 运行时 OpenAPI 统计为 **44 条路径 / 53 个操作**（同一路径可能同时有 GET 与 POST）\n")

    lines.append("## 鉴权方式\n")
    lines.append("```http")
    lines.append("POST /api/v1/auth/login        # {username, password} -> {access_token, user}")
    lines.append("Authorization: Bearer <access_token>   # 之后所有请求带上")
    lines.append("```\n")
    lines.append(
        "角色共四种：`admin` 管理员 / `doctor` 医生 / `nurse` 护士 / `viewer01` 只读。"
        "越权访问统一返回 `403 PERMISSION_DENIED`，并写入审计日志。\n"
    )

    lines.append("## 接口总表\n")
    for tag in sorted(groups, key=lambda t: (-len(groups[t]), t)):
        rows = sorted(groups[tag], key=lambda x: (METHOD_ORDER[x["method"].lower()], x["path"]))
        lines.append(f"### {tag}（{len(rows)}）\n")
        lines.append("| 方法 | 路径 | 用途 | 鉴权 |")
        lines.append("| --- | --- | --- | --- |")
        for it in rows:
            summary = (it["summary"] or "—").replace("|", "\\|")
            lines.append(f"| `{it['method']}` | `{it['path']}` | {summary} | {auth_text(it)} |")
        lines.append("")

    lines.append("## 统一错误格式\n")
    lines.append("```json")
    lines.append('{ "code": "BED_NOT_AVAILABLE", "message": "床位 C-101-01 当前状态为「已入住」，已被占用",')
    lines.append('  "detail": { "bed_id": 1, "status": "OCCUPIED" }, "request_id": "a05a82a314d5478d" }')
    lines.append("```\n")
    lines.append("| 状态码 | 典型 code | 含义 |")
    lines.append("| --- | --- | --- |")
    lines.append("| 400 | `VALIDATION_ERROR` | 参数校验失败 |")
    lines.append("| 401 | `UNAUTHENTICATED` | 未带令牌或令牌无效/过期 |")
    lines.append("| 403 | `PERMISSION_DENIED` | 角色不足（会写审计） |")
    lines.append("| 404 | `NOT_FOUND` | 资源不存在 |")
    lines.append("| 409 | `ILLEGAL_STATE_TRANSITION` / `BED_NOT_AVAILABLE` / `REQUEST_ALREADY_ALLOCATED` | 状态机或并发冲突 |")
    lines.append("| 422 | `HARD_CONSTRAINT_VIOLATION` | 违反硬约束（科室 / 性别 / 隔离） |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只校验 API.md 是否与源码一致")
    args = parser.parse_args()

    content = render(collect())
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current.strip() != content.strip():
            print("API.md 已过期，请重新运行 python scripts/gen_api_md.py")
            return 1
        print("API.md 与源码一致")
        return 0

    OUT.write_text(content, encoding="utf-8")
    print(f"写入 {OUT.name}（{len(collect())} 个端点）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
