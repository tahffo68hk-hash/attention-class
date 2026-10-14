"""Non-destructive regression: demo reset table list follows M1 schema."""
from app.services.allocation import _fingerprint_reservation
from seed import TABLES_IN_DELETE_ORDER


def test_seed_clears_idempotency_before_allocations():
    assert TABLES_IN_DELETE_ORDER.index('allocation_idempotency') < TABLES_IN_DELETE_ORDER.index('bed_allocations')


def test_idempotency_keys_are_scoped_by_actor():
    params=(21,7,False,'example')
    assert _fingerprint_reservation(*params,operator_id=1) != _fingerprint_reservation(*params,operator_id=2)
    assert _fingerprint_reservation(*params,operator_id=1) == _fingerprint_reservation(*params,operator_id=1)
