"""P1 实际纯算法测试；无 MySQL / 没有真实患者数据。"""
from __future__ import annotations
import itertools
import random
from math import nan, inf
import pytest
from app.services.global_optimization import EdgeCandidate as E, greedy, optimize, compare


def brute_objective(edges, ids):
    grouped = {x: [c for c in edges if c.request_id == x] for x in ids}
    best = (-1, -1, -1)
    for choices in itertools.product(*[[None, *grouped[x]] for x in ids]):
        used = [c.bed_id for c in choices if c]
        if len(set(used)) != len(used):
            continue
        selected = [c for c in choices if c]
        obj = (len(selected), sum(c.priority_rank for c in selected), sum(round(c.score * 100) for c in selected))
        best = max(best, obj)
    return best


def test_global_can_admit_more_than_greedy():
    edges = [E(1, 10, 5, 99), E(1, 20, 5, 98), E(2, 10, 1, 97)]
    baseline, optimal = compare(edges, [1,2])
    assert baseline.admitted == 1
    assert optimal.admitted == 2
    assert {(p.request_id, p.bed_id) for p in optimal.pairs} == {(1,20),(2,10)}
    assert optimal.proven_optimal


def test_priority_before_score():
    edges = [E(1, 10, 5, 5), E(2, 10, 1, 100)]
    answer = optimize(edges, [1,2], "flow")
    assert answer.pairs[0].request_id == 1


def test_one_bed_one_request_and_one_request_one_bed():
    edges = [E(1, 10, 5, 90), E(1, 20, 5, 80), E(2, 10, 4, 90), E(2, 20, 4, 89)]
    result = optimize(edges, [1,2], "flow")
    assert len({p.bed_id for p in result.pairs}) == result.admitted
    assert len({p.request_id for p in result.pairs}) == result.admitted


def test_empty_and_repeat_are_deterministic():
    result = optimize([], [1,2], "flow")
    assert result.admitted == 0 and result.unmatched_request_ids == (1,2)
    edges = [E(1, 3, 2, 70),E(1, 4, 2, 70),E(2, 3, 2, 70),E(2, 4, 2, 70)]
    pairings = [optimize(edges, [1,2], "flow").pairs for _ in range(5)]
    assert all(pairings[0] == x for x in pairings)


@pytest.mark.parametrize('edges,ids', [
    ([E(1,1,2,nan)],[1]),
    ([E(1,1,2,inf)],[1]),
    ([E(1,1,2,-1)],[1]),
    ([E(1,1,2,101)],[1]),
    ([E(1,1,6,1)],[1]),
    ([E(2,1,2,1)],[1]),
    ([E(1,1,2,5),E(1,1,2,6)],[1]),
    ([E(1,1,2,5),E(1,2,3,5)],[1]),
    ([],[1,1]),
    ([],[]),
])
def test_invalid_edges(edges, ids):
    with pytest.raises(ValueError):
        optimize(edges, ids, "flow")


def test_exact_matches_bruteforce_random_small_instances():
    rng = random.Random(20261014)
    for _ in range(75):
        requests = list(range(1,rng.randint(2,5)))
        beds = list(range(20,20+rng.randint(1,5)))
        ranks = {r:rng.randint(1,5) for r in requests}
        edges = [E(r,b,ranks[r],float(rng.randint(0,100)))
                 for r in requests for b in beds if rng.random()<0.7]
        actual = optimize(edges,requests, "flow")
        actual_obj = (actual.admitted,actual.priority_sum,round(actual.score_sum*100))
        assert actual_obj == brute_objective(edges,requests), (edges, actual)


def test_large_bounded_case():
    edges=[E(r,b,1+(r%5),float((r*13+b*7)%101)) for r in range(1,25) for b in range(1,16)]
    result=optimize(edges,list(range(1,25)),"flow")
    assert result.admitted==15
    assert result.proven_optimal


def test_solver_unavailable_is_explicit():
    try:
        import ortools  # noqa
    except ImportError:
        with pytest.raises(RuntimeError, match="CP-SAT"):
            optimize([E(1,1,1,80)],[1],"cp_sat")


def test_auto_defaults_to_exact_flow_even_when_cp_sat_is_available(monkeypatch):
    # Optional solver should never silently add a 5-second deadline to auto requests.
    import app.services.global_optimization as engine
    def should_not_be_called(*args, **kwargs):
        raise AssertionError("auto unexpectedly used CP-SAT")
    monkeypatch.setattr(engine, "_ortools_solver", should_not_be_called)
    result = optimize([E(1, 2, 5, 93)], [1], backend="auto")
    assert result.method == "exact_min_cost_flow"
    assert result.proven_optimal and result.admitted == 1


@pytest.mark.parametrize("invalid", [
    E(1, True, 5, 80), E(True, 2, 5, 80), E(1, 2, 5, True),
])
def test_strict_numeric_validation_rejects_booleans(invalid):
    with pytest.raises(ValueError):
        optimize([invalid], [1], backend="flow")


def test_exact_matches_bruteforce_fractional_scores():
    rng = random.Random(77110)
    for _ in range(50):
        ids = [1, 2, 3]
        rank = {r: rng.randint(1, 5) for r in ids}
        edges = [E(r, b, rank[r], rng.randint(0, 10000) / 100)
                 for r in ids for b in (10, 20, 30) if rng.random() < 0.8]
        result = optimize(edges, ids, "flow")
        assert (result.admitted, result.priority_sum, round(result.score_sum * 100)) == brute_objective(edges, ids)
