"""P1 多患者床位联合匹配（纯函数）。

先最大化成功匹配人数，再最大化已匹配患者优先级之和，最后最大化
原五维推荐得分之和。对完全相同目标的可行解使用稳定边序进行确定性选择。
算法为容量 1 的最小费用最大流；无 OR-Tools 也可在 CPU 上运行。
可选 CP-SAT 求解器仅在取得 OPTIMAL 时采用，否则回退到精确流算法。
此模块不访问数据库，也绝不执行床位写入。
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from time import perf_counter
from typing import Literal

MAX_REQUESTS = 30
MAX_BEDS = 100
MAX_EDGES = 2000


@dataclass(frozen=True)
class EdgeCandidate:
    request_id: int
    bed_id: int
    priority_rank: int  # 1..5
    score: float  # already passed H1-H4, 0..100


@dataclass(frozen=True)
class MatchedPair:
    request_id: int
    bed_id: int
    priority_rank: int
    score: float


@dataclass(frozen=True)
class Solution:
    method: str
    pairs: tuple[MatchedPair, ...]
    unmatched_request_ids: tuple[int, ...]
    admitted: int
    priority_sum: int
    score_sum: float
    runtime_ms: float
    proven_optimal: bool


@dataclass
class _Arc:
    to: int
    rev: int
    capacity: int
    cost: int


def validate_candidates(candidates: list[EdgeCandidate], request_ids: list[int]) -> tuple[list[EdgeCandidate], list[int], list[int]]:
    if not request_ids or len(request_ids) > MAX_REQUESTS or len(set(request_ids)) != len(request_ids):
        raise ValueError(f"住院申请数量必须为 1–{MAX_REQUESTS} 且不得重复")
    if any(not isinstance(x, int) or isinstance(x, bool) or x <= 0 for x in request_ids):
        raise ValueError("住院申请 ID 必须为正整数")
    unique: set[tuple[int, int]] = set()
    priority: dict[int, int] = {}
    beds: set[int] = set()
    if len(candidates) > MAX_EDGES:
        raise ValueError(f"候选关系超过 {MAX_EDGES}，请缩小批次")
    for c in candidates:
        if (not isinstance(c.request_id, int) or isinstance(c.request_id, bool)
                or c.request_id not in request_ids or not isinstance(c.bed_id, int)
                or isinstance(c.bed_id, bool) or c.bed_id <= 0):
            raise ValueError("候选包含非法住院申请或床位 ID")
        if not isinstance(c.priority_rank, int) or isinstance(c.priority_rank, bool) or not 1 <= c.priority_rank <= 5:
            raise ValueError("优先级必须为 1–5")
        if (not isinstance(c.score, (float, int)) or isinstance(c.score, bool)
                or not isfinite(c.score) or not 0 <= c.score <= 100):
            raise ValueError("候选分数必须为 0–100 的有限实数")
        if (c.request_id, c.bed_id) in unique:
            raise ValueError("住院申请与床位候选不可重复")
        unique.add((c.request_id, c.bed_id))
        if c.request_id in priority and priority[c.request_id] != c.priority_rank:
            raise ValueError("同一住院证优先级不一致")
        priority[c.request_id] = c.priority_rank
        beds.add(c.bed_id)
    if len(beds) > MAX_BEDS:
        raise ValueError(f"候选床位数超过 {MAX_BEDS}")
    return sorted(candidates, key=lambda c: (c.request_id, c.bed_id)), sorted(request_ids), sorted(beds)


def _assemble(method: str, started: float, pairs: list[MatchedPair], ids: list[int], optimal: bool) -> Solution:
    pairs.sort(key=lambda p: (p.request_id, p.bed_id))
    matched = {p.request_id for p in pairs}
    return Solution(
        method=method, pairs=tuple(pairs),
        unmatched_request_ids=tuple(x for x in ids if x not in matched),
        admitted=len(pairs), priority_sum=sum(p.priority_rank for p in pairs),
        score_sum=round(sum(p.score for p in pairs), 2),
        runtime_ms=round((perf_counter() - started) * 1000, 3),
        proven_optimal=optimal,
    )


def greedy(candidates: list[EdgeCandidate], request_ids: list[int]) -> Solution:
    started = perf_counter()
    edges, ids, _ = validate_candidates(candidates, request_ids)
    rank = {x.request_id: x.priority_rank for x in edges}
    by_request: dict[int, list[EdgeCandidate]] = {i: [] for i in ids}
    for c in edges:
        by_request[c.request_id].append(c)
    beds_taken: set[int] = set()
    output: list[MatchedPair] = []
    for i in sorted(ids, key=lambda i: (-rank.get(i, 0), i)):
        for candidate in sorted(by_request[i], key=lambda c: (-c.score, c.bed_id)):
            if candidate.bed_id not in beds_taken:
                beds_taken.add(candidate.bed_id)
                output.append(MatchedPair(candidate.request_id, candidate.bed_id, candidate.priority_rank, candidate.score))
                break
    return _assemble("greedy", started, output, ids, False)


def _weight(edge: EdgeCandidate, index: int, count: int, n_edges: int) -> int:
    # Lexicographic units: one extra match dominates all priority/score/ties;
    # one extra priority point dominates any feasible score/tie variation.
    tie_max = count * (n_edges + 1)
    score_unit = tie_max + 1
    priority_unit = count * 10000 * score_unit + tie_max + 1
    match_unit = count * 5 * priority_unit + count * 10000 * score_unit + tie_max + 1
    score_cents = round(edge.score * 100)
    return match_unit + edge.priority_rank * priority_unit + score_cents * score_unit + (n_edges - index)


def _flow_solver(edges: list[EdgeCandidate], ids: list[int], beds: list[int]) -> list[MatchedPair]:
    r_nodes = {r: i + 1 for i, r in enumerate(ids)}
    b_nodes = {b: len(ids) + i + 1 for i, b in enumerate(beds)}
    sink = len(ids) + len(beds) + 1
    graph: list[list[_Arc]] = [[] for _ in range(sink + 1)]

    def add(u: int, v: int, cap: int, cost: int) -> int:
        index = len(graph[u])
        graph[u].append(_Arc(v, len(graph[v]), cap, cost))
        graph[v].append(_Arc(u, index, 0, -cost))
        return index

    for r in ids:
        add(0, r_nodes[r], 1, 0)
    for b in beds:
        add(b_nodes[b], sink, 1, 0)
    edge_locations: list[tuple[EdgeCandidate, int, int]] = []
    for index, c in enumerate(edges):
        u = r_nodes[c.request_id]
        arc_index = add(u, b_nodes[c.bed_id], 1, -_weight(c, index, len(ids), len(edges)))
        edge_locations.append((c, u, arc_index))

    # Bellman-Ford shortest augmenting paths with deterministic iteration.
    # A simple exact polynomial baseline suitable for this bounded prototype.
    while True:
        distances: list[int | None] = [None] * len(graph)
        prev: list[tuple[int, int] | None] = [None] * len(graph)
        distances[0] = 0
        for _ in range(len(graph) - 1):
            changed = False
            for u, arcs in enumerate(graph):
                if distances[u] is None:
                    continue
                for ai, arc in enumerate(arcs):
                    if arc.capacity <= 0:
                        continue
                    new_cost = distances[u] + arc.cost
                    if distances[arc.to] is None or new_cost < distances[arc.to]:
                        distances[arc.to] = new_cost
                        prev[arc.to] = (u, ai)
                        changed = True
            if not changed:
                break
        if distances[sink] is None or distances[sink] >= 0:
            break
        node = sink
        steps = 0
        while node != 0:
            if prev[node] is None or steps > len(graph):
                raise RuntimeError("残量网络回溯异常")
            u, ai = prev[node]
            arc = graph[u][ai]
            arc.capacity -= 1
            graph[node][arc.rev].capacity += 1
            node = u
            steps += 1
    return [MatchedPair(c.request_id, c.bed_id, c.priority_rank, c.score)
            for c, u, ai in edge_locations if graph[u][ai].capacity == 0]


def _ortools_solver(edges: list[EdgeCandidate], ids: list[int], beds: list[int]) -> list[MatchedPair] | None:
    """Optional CP-SAT; only an OPTIMAL certificate is accepted."""
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return None
    model = cp_model.CpModel()
    variables = [model.new_bool_var(f"x_{i}") for i in range(len(edges))]
    for r in ids:
        model.add(sum(variables[i] for i, c in enumerate(edges) if c.request_id == r) <= 1)
    for b in beds:
        model.add(sum(variables[i] for i, c in enumerate(edges) if c.bed_id == b) <= 1)
    model.maximize(sum(_weight(c, i, len(ids), len(edges)) * variables[i] for i, c in enumerate(edges)))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    status = solver.solve(model)
    if status != cp_model.OPTIMAL:
        return None
    return [MatchedPair(c.request_id, c.bed_id, c.priority_rank, c.score)
            for i, c in enumerate(edges) if solver.value(variables[i]) == 1]


def optimize(candidates: list[EdgeCandidate], request_ids: list[int], backend: Literal["auto", "flow", "cp_sat"] = "auto") -> Solution:
    started = perf_counter()
    edges, ids, beds = validate_candidates(candidates, request_ids)
    pairs: list[MatchedPair] | None = None
    engine = "exact_min_cost_flow"
    if backend not in ("auto", "flow", "cp_sat"):
        raise ValueError("未识别的优化后端")
    # The bounded exact flow solver is fast and predictable; only an explicit
    # CP-SAT choice incurs a potentially multi-second CP-SAT invocation.
    if backend == "cp_sat" and edges:
        pairs = _ortools_solver(edges, ids, beds)
        if pairs is not None:
            engine = "ortools_cp_sat"
        elif backend == "cp_sat":
            raise RuntimeError("CP-SAT 未安装或未能在时间限制内证明最优")
    if pairs is None:
        pairs = _flow_solver(edges, ids, beds)
    return _assemble(engine, started, pairs, ids, True)


def compare(candidates: list[EdgeCandidate], request_ids: list[int]) -> tuple[Solution, Solution]:
    return greedy(candidates, request_ids), optimize(candidates, request_ids)
