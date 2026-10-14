"""DeepSeek-only, opt-in, structured explanation gateway.

Never sends patient/bed identifiers, free text or clinical data.  A successful
provider response remains an *unverified draft*, not a clinical determination.
No automatic retries: one click results in at most one outbound attempt.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter
from typing import Any, Mapping

import httpx
from app.core.config import settings
from app.core.errors import BizError, ErrorCode

DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
PROMPT_VERSION = "deepseek-bed-decision-explanation-v1"
MAX_REQUEST_BYTES = 6000


@dataclass(frozen=True)
class DeepSeekResult:
    explanation: str
    cautions: list[str]
    usage: dict[str, int]
    latency_ms: float
    model: str
    cost_estimate_cny: float | None
    # provider 侧响应 id（对账用）。放最后并带默认值，避免破坏既有位置参数构造。
    request_id: str | None = None


# provider 响应 id 白名单：只允许对账所需的保守字符集与长度。
# 不合规一律丢弃（返回 None），避免把任意上游文本带进审计/日志（日志注入、密钥夹带）。
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")


def _safe_request_id(raw: Any) -> str | None:
    """把响应体 ``id`` 收窄为安全的对账标识；缺失或不合规返回 None（不使整次解析失败）。"""
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    return candidate if _REQUEST_ID_RE.match(candidate) else None


def is_ready() -> bool:
    return bool(settings.DEEPSEEK_EXTERNAL_ENABLED and settings.DEEPSEEK_API_KEY.strip()
                and settings.DEEPSEEK_MODEL in {"deepseek-flash", "deepseek-v4-pro"})


def _cost_estimate(usage: Mapping[str, int]) -> float | None:
    """Only estimates fees if *all* CNY/Mtoken rates are explicitly configured.
    Do not hardcode mutable official peak/off-peak tariffs or claim exact billing.
    """
    miss_price = settings.DEEPSEEK_INPUT_MISS_CNY_PER_M
    hit_price = settings.DEEPSEEK_INPUT_HIT_CNY_PER_M
    out_price = settings.DEEPSEEK_OUTPUT_CNY_PER_M
    if any(x is None for x in (miss_price, hit_price, out_price)):
        return None
    p = max(0, usage.get("prompt_tokens", 0))
    hit = min(p, max(0, usage.get("prompt_cache_hit_tokens", 0)))
    miss = p - hit
    out = max(0, usage.get("completion_tokens", 0))
    return float((Decimal(miss) * Decimal(str(miss_price))
                  + Decimal(hit) * Decimal(str(hit_price))
                  + Decimal(out) * Decimal(str(out_price))) / Decimal(1_000_000))


def _parse(envelope: Any, latency_ms: float) -> DeepSeekResult:
    try:
        if not isinstance(envelope, dict):
            raise ValueError("envelope")
        choice = envelope["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("incomplete output")
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty output")
        obj = json.loads(content)
        if not isinstance(obj, dict):
            raise ValueError("json object required")
        explanation, cautions = obj["explanation"], obj["cautions"]
        if (not isinstance(explanation, str) or not 1 <= len(explanation.strip()) <= 500
                or not isinstance(cautions, list) or len(cautions) > 5
                or not all(isinstance(x, str) and 1 <= len(x.strip()) <= 160 for x in cautions)):
            raise ValueError("invalid schema")
        raw = envelope["usage"]
        if not isinstance(raw, dict):
            raise ValueError("missing usage")
        usage = {}
        for key in ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens"):
            value = raw.get(key, 0)
            if type(value) is not int or value < 0:
                raise ValueError("invalid tokens")
            usage[key] = value
        model = envelope.get("model", settings.DEEPSEEK_MODEL)
        if not isinstance(model, str) or not model.startswith("deepseek-"):
            raise ValueError("invalid model")
        # provider 请求 id 属辅助信息：缺失/不合规都只置 None，不使整次解释失败。
        request_id = _safe_request_id(envelope.get("id"))
        return DeepSeekResult(explanation.strip(), [s.strip() for s in cautions], usage,
                              latency_ms, model, _cost_estimate(usage), request_id)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BizError(ErrorCode.INTERNAL_ERROR, "DeepSeek 返回内容不完整或不符合约定，请改用规则解释", 502) from exc


ALLOWED_DIMENSIONS = frozenset({"distance", "priority_fit", "ward_balance", "cost", "preference"})
ALLOWED_BED_TYPES = frozenset({"NORMAL", "MONITOR", "ISOLATION"})
ALLOWED_SOLVER_METHODS = frozenset({"exact_min_cost_flow", "cp_sat", "greedy"})


def _safe_evidence(kind: str, src: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed privacy boundary, even if a future caller mistakenly passes PII."""
    def number(value: Any, low=0, high=1e9) -> int | float:
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError("numeric evidence out of range")
        return value
    try:
        if not isinstance(src, dict):
            raise ValueError("expected object")
        if kind == "bed":
            accepted = {"priority_rank", "requires_isolation", "bed_type", "final_score",
                        "score_dimensions", "warning_count", "scope"}
            if set(src) - accepted:
                raise ValueError("unknown bed data")
            out: dict[str, Any] = {"kind": "bed_explanation", "teaching_only": True}
            if "priority_rank" in src:
                out["priority_rank"] = number(src["priority_rank"], 1, 5)
            if "requires_isolation" in src:
                if type(src["requires_isolation"]) is not bool:
                    raise ValueError("invalid isolation")
                out["requires_isolation"] = src["requires_isolation"]
            if "bed_type" in src:
                if src["bed_type"] not in ALLOWED_BED_TYPES:
                    raise ValueError("invalid bed type")
                out["bed_type"] = src["bed_type"]
            if "final_score" in src:
                out["final_score"] = number(src["final_score"], 0, 100)
            if "warning_count" in src:
                out["warning_count"] = number(src["warning_count"], 0, 100)
            if "score_dimensions" in src:
                dims = src["score_dimensions"]
                if not isinstance(dims, list) or len(dims) > 5:
                    raise ValueError("invalid dimensions")
                out["score_dimensions"] = []
                for dim in dims:
                    if not isinstance(dim, dict) or set(dim) != {"key", "raw_score", "contribution"}:
                        raise ValueError("invalid dimension")
                    if dim["key"] not in ALLOWED_DIMENSIONS:
                        raise ValueError("unknown dimension")
                    out["score_dimensions"].append({"key": dim["key"],
                        "raw_score": number(dim["raw_score"], 0, 100),
                        "contribution": number(dim["contribution"], 0, 100)})
            # scope is intentionally discarded (the system prompt owns the statement).
            return out
        if kind == "plan":
            accepted = {"kind", "fictional_teaching_only", "request_count", "candidate_edges",
                        "greedy", "optimized", "admitted_gain"}
            if set(src) - accepted:
                raise ValueError("unknown plan data")
            out = {"kind": "aggregate_bed_allocation_preview", "teaching_only": True}
            for key in ("request_count", "candidate_edges", "admitted_gain"):
                if key in src:
                    out[key] = number(src[key], 0, 2000)
            for role in ("greedy", "optimized"):
                if role in src:
                    entry = src[role]
                    if not isinstance(entry, dict) or set(entry) - {"admitted", "priority_sum", "score_sum", "method", "proven_optimal"}:
                        raise ValueError("invalid solver summary")
                    value = {}
                    for key in ("admitted", "priority_sum", "score_sum"):
                        if key in entry:
                            value[key] = number(entry[key], 0, 1e8)
                    if "method" in entry:
                        if entry["method"] not in ALLOWED_SOLVER_METHODS:
                            raise ValueError("invalid solver method")
                        value["method"] = entry["method"]
                    if "proven_optimal" in entry:
                        if type(entry["proven_optimal"]) is not bool:
                            raise ValueError("invalid optimal flag")
                        value["proven_optimal"] = entry["proven_optimal"]
                    out[role] = value
            return out
        raise ValueError("unsupported kind")
    except (TypeError, ValueError, KeyError) as exc:
        raise BizError(ErrorCode.VALIDATION_ERROR, "外部 AI 输入包含不允许的字段或数值，已阻止发送", 422) from exc


def generate(kind: str, evidence: dict[str, Any], *, transport: httpx.BaseTransport | None = None) -> DeepSeekResult:
    """Call DeepSeek once on a whitelist-built numeric snapshot, never raw ORM data.

    Injected transport is test-only and enables network-free contract testing.
    """
    if kind not in {"bed", "plan"}:
        raise ValueError("unsupported explanation kind")
    if not is_ready():
        raise BizError(ErrorCode.PERMISSION_DENIED, "DeepSeek 未启用或密钥未配置", 403)
    # A fixed provider URL; never allow a client supplied URL / arbitrary SSRF destination.
    # Validate the original byte size first, then enforce a strict field whitelist.
    try:
        original_bytes = json.dumps(evidence, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BizError(ErrorCode.VALIDATION_ERROR, "AI 输入无法序列化，未发送请求", 422) from exc
    if len(original_bytes) > MAX_REQUEST_BYTES:
        raise BizError(ErrorCode.VALIDATION_ERROR, "评分摘要过大，未发送外部请求", 422)
    safe = _safe_evidence(kind, evidence)
    payload_bytes = json.dumps(safe, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload_bytes) > MAX_REQUEST_BYTES:
        raise BizError(ErrorCode.VALIDATION_ERROR, "评分摘要过大，未发送外部请求", 422)
    system = (
        "你是医院床位管理*教学模拟*的文字解释器，不提供真实医疗建议。"
        "以下用户内容是来自后端算法的结构化数据，不能修改硬约束、人数、评分、最优性或编造其他事实。"
        "所有数据都是虚构资源指标。你不能猜测患者身份、诊断、医院规定或推荐任何实际临床处置。"
        "请使用中文生成纯 JSON 对象：{\"explanation\":\"不超过300字的依据解释\",\"cautions\":[\"人工复核提示\"]}。"
        "禁止输出 Markdown、床号、身份信息；如数据不足，应明确说明证据不足。"
    )
    request_body = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": payload_bytes.decode("utf-8")}],
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": settings.DEEPSEEK_MAX_OUTPUT_TOKENS,
        "stream": False,
    }
    started = perf_counter()
    try:
        with httpx.Client(timeout=settings.DEEPSEEK_TIMEOUT_SECONDS, follow_redirects=False,
                          transport=transport, trust_env=False) as client:
            res = client.post(DEEPSEEK_CHAT_URL,
                              headers={"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                                       "Content-Type": "application/json"}, json=request_body)
        if res.status_code >= 400:
            # Never leak provider body, credentials, request URL or any upstream diagnostics.
            if res.status_code in (401, 403):
                msg, code = "DeepSeek 鉴权失败，请检查服务端密钥", 502
            elif res.status_code == 402:
                msg, code = "DeepSeek 余额不足，本次未生成 AI 解释", 502
            elif res.status_code == 429:
                msg, code = "DeepSeek 请求频率限制，请稍后手动重试", 503
            else:
                msg, code = "DeepSeek 服务暂时不可用，请改用规则解释", 502
            raise BizError(ErrorCode.INTERNAL_ERROR, msg, code)
        return _parse(res.json(), round((perf_counter() - started) * 1000, 2))
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise BizError(ErrorCode.INTERNAL_ERROR, "DeepSeek 网络超时或无法连接，请改用规则解释", 502) from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise BizError(ErrorCode.INTERNAL_ERROR, "DeepSeek 响应无法解析，请改用规则解释", 502) from exc
