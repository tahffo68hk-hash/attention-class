"""P1.5 synthetic dispatch research; NO database writes, NO clinical data.

Uses the existing hard_constraint_violations and five score-component functions
from the production recommendation service. Synthetic coordinates, costs and
ward availability are fixed at the beginning of each scenario; the scores
are a static planning snapshot, not dynamic scores after individual bookings.

Run:
 PYTHONPATH=backend python scripts/benchmark_matrix.py --output-dir docs/experiments/p15
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.models.enums import PatientPriority, PRIORITY_RANK, BedStatus, BedType, GenderLimit
from app.services.bed_policy import hard_constraint_violations, distance_to_department
from app.services.recommendation import (
    PRIORITY_PROFILE, WEIGHTS, _score_distance, _score_priority_fit,
    _score_ward_balance, _score_cost, _score_preference,
)
from app.services.global_optimization import EdgeCandidate, greedy, optimize

PRIORITIES = tuple(PRIORITY_RANK)
COLUMNS = (
    'case_id', 'seed', 'patients', 'beds', 'supply_ratio', 'isolation_ratio',
    'available_ratio', 'candidate_edges', 'hard_constraint_rejections',
    'greedy_admitted', 'exact_admitted', 'admitted_gain',
    'greedy_priority_sum', 'exact_priority_sum', 'priority_gain',
    'greedy_score_sum', 'exact_score_sum', 'score_gain',
    'greedy_high_priority_served', 'exact_high_priority_served',
    'greedy_high_priority_rate', 'exact_high_priority_rate',
    'greedy_ms', 'exact_ms', 'candidate_digest',
)


@dataclass(frozen=True)
class CaseSpec:
    patients: int
    supply_ratio: float
    isolation_ratio: float
    seed: int
    available_ratio: float = 0.9

    @property
    def beds(self) -> int:
        return max(1, min(100, round(self.patients * self.supply_ratio)))

    @property
    def case_id(self) -> str:
        return f'p{self.patients}_s{self.supply_ratio:.2f}_iso{self.isolation_ratio:.2f}_seed{self.seed}'


def matrix_specs(seeds: Iterable[int] = (20261014, 20261015, 20261016)) -> list[CaseSpec]:
    return [CaseSpec(n, supply, isolation, seed) for seed in seeds
            for n in (8, 16, 30)
            for supply in (0.65, 1.0, 1.4)
            for isolation in (0.10, 0.35, 0.60)]


def build_case(spec: CaseSpec) -> tuple[list[int], list[EdgeCandidate], int, int]:
    """Generate all eligible pairs using production H1-H4 and five score components.

    Deliberately varies department, gender, isolation, bed status and care type.
    All attributes are fictional and never persisted to the application DB.
    """
    if not 1 <= spec.patients <= 30 or not 0 < spec.supply_ratio or not 0 <= spec.isolation_ratio <= 1:
        raise ValueError('invalid experiment specification')
    if not 0 <= spec.available_ratio <= 1:
        raise ValueError('invalid availability')
    rng = random.Random(spec.seed * 1009 + spec.patients * 113 +
                        round(spec.supply_ratio * 100) * 23 + round(spec.isolation_ratio * 100) * 7)
    beds = []
    for index in range(spec.beds):
        department = 1 if rng.random() < 0.75 else 2
        isolation = rng.random() < spec.isolation_ratio
        floor = rng.choice((1, 2, 3))
        beds.append(SimpleNamespace(
            id=index + 1, department_id=department,
            status=BedStatus.AVAILABLE if rng.random() < spec.available_ratio else BedStatus.OCCUPIED,
            gender_limit=rng.choice((GenderLimit.ANY, GenderLimit.ANY, GenderLimit.MALE, GenderLimit.FEMALE)),
            is_isolation=isolation,
            bed_type=BedType.ISOLATION if isolation else rng.choice((BedType.NORMAL, BedType.NORMAL, BedType.MONITOR)),
            floor=floor, position_x=rng.randrange(0, 70), position_y=rng.randrange(0, 30),
            ward_id=department * 100 + (index % 4),
            daily_rate=Decimal(rng.randrange(80, 360)),
        ))
    ward_total = Counter(b.ward_id for b in beds)
    ward_free = Counter(b.ward_id for b in beds if b.status == BedStatus.AVAILABLE)
    all_edges: list[EdgeCandidate] = []
    rejected = 0
    high_priority_count = 0
    for request_id in range(1, spec.patients + 1):
        department_id = 1 if rng.random() < 0.75 else 2
        patient_gender = rng.choice(('MALE', 'FEMALE'))
        isolation_required = rng.random() < spec.isolation_ratio
        priority = rng.choice(PRIORITIES)
        rank = PRIORITY_RANK[priority]
        high_priority_count += int(rank >= 4)
        profile = PRIORITY_PROFILE[priority]
        dept = SimpleNamespace(anchor_floor=1 if department_id == 1 else 3,
                               anchor_x=0, anchor_y=0)
        allowed = []
        for bed in beds:
            violations = hard_constraint_violations(
                bed, department_id=department_id, patient_gender=patient_gender,
                isolation_required=isolation_required,
            )
            if violations:
                rejected += 1
            else:
                allowed.append(bed)
        rates = [bed.daily_rate for bed in allowed]
        low_rate, high_rate = (min(rates), max(rates)) if rates else (Decimal(0), Decimal(0))
        preferred_ward_id = department_id * 100 if rng.random() < 0.5 else None
        for bed in allowed:
            distance = distance_to_department(bed, dept)
            components = (
                _score_distance(distance, profile)[0],
                _score_priority_fit(bed, rank, priority)[0],
                _score_ward_balance(ward_free[bed.ward_id], ward_total[bed.ward_id])[0],
                _score_cost(bed.daily_rate, low_rate, high_rate, profile)[0],
                _score_preference(bed, preferred_ward_id)[0],
            )
            # Same order, per-item contribution rounding and final rounding as recommend_beds.
            weighted = sum(round(x * WEIGHTS[k], 4) for x, k in zip(components, WEIGHTS))
            score = round(max(0, min(100, weighted)), 2)
            all_edges.append(EdgeCandidate(request_id, bed.id, rank, score))
    return list(range(1, spec.patients + 1)), all_edges, rejected, high_priority_count


def candidate_digest(ids: list[int], edges: list[EdgeCandidate]) -> str:
    payload = {'ids': ids, 'edges': [(x.request_id, x.bed_id, x.priority_rank, x.score)
                                    for x in sorted(edges, key=lambda e: (e.request_id, e.bed_id))]}
    return hashlib.sha256(json.dumps(payload, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def run_case(spec: CaseSpec) -> dict:
    ids, edges, rejects, high_count = build_case(spec)
    baseline = greedy(edges, ids)
    exact = optimize(edges, ids, backend='flow')
    assert exact.proven_optimal
    assert (exact.admitted, exact.priority_sum, round(exact.score_sum * 100)) >= (
        baseline.admitted, baseline.priority_sum, round(baseline.score_sum * 100))
    def served(sol) -> int:
        return sum(p.priority_rank >= 4 for p in sol.pairs)
    a, b = served(baseline), served(exact)
    return dict(
        case_id=spec.case_id, seed=spec.seed, patients=spec.patients,
        beds=spec.beds, supply_ratio=spec.supply_ratio,
        isolation_ratio=spec.isolation_ratio, available_ratio=spec.available_ratio,
        candidate_edges=len(edges), hard_constraint_rejections=rejects,
        greedy_admitted=baseline.admitted, exact_admitted=exact.admitted,
        admitted_gain=exact.admitted - baseline.admitted,
        greedy_priority_sum=baseline.priority_sum, exact_priority_sum=exact.priority_sum,
        priority_gain=exact.priority_sum - baseline.priority_sum,
        greedy_score_sum=baseline.score_sum, exact_score_sum=exact.score_sum,
        score_gain=round(exact.score_sum - baseline.score_sum, 2),
        greedy_high_priority_served=a, exact_high_priority_served=b,
        greedy_high_priority_rate=round(a / high_count, 4) if high_count else None,
        exact_high_priority_rate=round(b / high_count, 4) if high_count else None,
        greedy_ms=baseline.runtime_ms, exact_ms=exact.runtime_ms,
        candidate_digest=candidate_digest(ids, edges),
    )


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    position = (len(values) - 1) * pct
    lower = int(position)
    frac = position - lower
    return values[lower] * (1 - frac) + values[min(lower + 1, len(values) - 1)] * frac


def summary(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError('no experiments')
    exact_times = [x['exact_ms'] for x in rows]
    greedy_times = [x['greedy_ms'] for x in rows]
    out = {
        'dataset': 'SYNTHETIC_ONLY', 'clinical_validation': False,
        'score_origin': 'existing H1-H4 and five-dimensional functions',
        'objective': 'lexicographic(admitted,priority_sum,score_sum)',
        'number_of_cases': len(rows),
        'total_greedy_admitted': sum(x['greedy_admitted'] for x in rows),
        'total_exact_admitted': sum(x['exact_admitted'] for x in rows),
        'cases_admission_improved': sum(x['admitted_gain'] > 0 for x in rows),
        'cases_priority_improved_with_equal_admissions': sum(
            x['admitted_gain'] == 0 and x['priority_gain'] > 0 for x in rows),
        'greedy_time_ms_median': round(statistics.median(greedy_times), 3),
        'greedy_time_ms_p95': round(percentile(greedy_times, .95), 3),
        'exact_time_ms_median': round(statistics.median(exact_times), 3),
        'exact_time_ms_p95': round(percentile(exact_times, .95), 3),
    }
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        key = f"supply={r['supply_ratio']:.2f},isolation={r['isolation_ratio']:.2f}"
        grouped.setdefault(key, []).append(r)
    out['by_supply_isolation'] = {k: {
        'cases': len(g), 'average_admitted_gain': round(statistics.mean(x['admitted_gain'] for x in g), 3),
        'average_exact_fill_rate': round(statistics.mean(x['exact_admitted'] / x['beds'] for x in g), 3),
        'exact_ms_p95': round(percentile([x['exact_ms'] for x in g], .95), 3),
    } for k, g in sorted(grouped.items())}
    return out


def run(output_dir: Path, *, seeds: Iterable[int] = (20261014, 20261015, 20261016)) -> tuple[list[dict], dict]:
    rows = [run_case(spec) for spec in matrix_specs(seeds)]
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / 'scenario_results.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    metrics = summary(rows)
    (output_dir / 'summary.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return rows, metrics


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='多场景床位调度合成实验')
    ap.add_argument('--output-dir', type=Path, default=ROOT / 'docs' / 'experiments' / 'p15')
    ap.add_argument('--seeds', nargs='+', type=int, default=[20261014, 20261015, 20261016])
    args = ap.parse_args()
    data, metrics = run(args.output_dir, seeds=args.seeds)
    print(f"{len(data)} scenarios; greedy admitted={metrics['total_greedy_admitted']}; "
          f"exact admitted={metrics['total_exact_admitted']}; "
          f"median/p95 exact={metrics['exact_time_ms_median']}/{metrics['exact_time_ms_p95']} ms")
