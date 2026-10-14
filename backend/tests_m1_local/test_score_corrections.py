"""Pure five-dimensional scoring checks; these change a documented heuristic, not clinical advice."""
from decimal import Decimal
from app.models.enums import PatientPriority
from app.services.recommendation import (
    WEIGHTS, PRIORITY_PROFILE, _score_cost, _score_distance
)


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values())-1.0)<1e-12
    assert set(WEIGHTS)=={'distance','priority_fit','ward_balance','cost','preference'}


def test_price_sensitivity_has_correct_direction():
    low, high=Decimal('100'),Decimal('500')
    for priority in PatientPriority:
        profile=PRIORITY_PROFILE[priority.value]
        cheap,_=_score_cost(low,low,high,profile)
        expensive,_=_score_cost(high,low,high,profile)
        assert cheap == 100
        assert cheap >= expensive >= 0
    # "越在意费用" 必须受到更大而非更小的高价格惩罚。
    severe,_=_score_cost(high,low,high,PRIORITY_PROFILE[PatientPriority.CRITICAL])
    mild,_=_score_cost(high,low,high,PRIORITY_PROFILE[PatientPriority.MILD])
    assert mild < severe


def test_distances_have_documented_direction():
    critical=PRIORITY_PROFILE[PatientPriority.CRITICAL]
    mild=PRIORITY_PROFILE[PatientPriority.MILD]
    assert _score_distance(1,critical)[0]>_score_distance(20,critical)[0]
    assert _score_distance(20,mild)[0]>_score_distance(1,mild)[0]
