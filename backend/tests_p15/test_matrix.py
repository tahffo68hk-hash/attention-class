from __future__ import annotations
import csv
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_matrix import CaseSpec, matrix_specs, build_case, run_case, run, candidate_digest, summary
from app.services.global_optimization import greedy, optimize


def test_matrix_crosses_supply_and_isolation_and_sizes():
    specs = matrix_specs((31,32))
    assert len(specs) == 54
    assert {s.patients for s in specs} == {8,16,30}
    assert {s.isolation_ratio for s in specs} == {.1,.35,.6}
    assert {s.supply_ratio for s in specs} == {.65,1.,1.4}


def test_repeated_generation_is_bitwise_deterministic():
    spec = CaseSpec(16, 1., .35, 20261014)
    a = build_case(spec)
    b = build_case(spec)
    assert a == b
    assert candidate_digest(a[0], a[1]) == candidate_digest(b[0], b[1])
    assert all(0 <= e.score <= 100 for e in a[1])


def test_optimizer_preserves_lexicographic_objective():
    for spec in matrix_specs((20261014,)):
        ids, edges, _, _ = build_case(spec)
        g, e = greedy(edges,ids), optimize(edges,ids)
        assert len(set(p.bed_id for p in e.pairs)) == e.admitted
        assert len(set(p.request_id for p in e.pairs)) == e.admitted
        assert (e.admitted,e.priority_sum,round(e.score_sum * 100)) >= (g.admitted,g.priority_sum,round(g.score_sum * 100))


def test_empty_candidate_pool_and_no_division_error():
    result = run_case(CaseSpec(8, .65, .0, 12, available_ratio=0.))
    assert result['candidate_edges'] == 0
    assert result['exact_admitted'] == 0
    assert result['greedy_admitted'] == 0


def test_results_csv_json_and_provenance(tmp_path):
    rows, result = run(tmp_path, seeds=(17,))
    assert len(rows) == 27
    assert result['number_of_cases'] == 27
    assert result['clinical_validation'] is False
    assert len(result['by_supply_isolation']) == 9
    with (tmp_path/'scenario_results.csv').open(encoding='utf-8') as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) == 27
    assert csv_rows[0]['candidate_digest'] == rows[0]['candidate_digest']
    assert json.loads((tmp_path/'summary.json').read_text(encoding='utf-8')) == result
    assert result['total_exact_admitted'] >= result['total_greedy_admitted']
