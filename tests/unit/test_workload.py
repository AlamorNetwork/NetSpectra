"""Golden vector fixes generator behavior across Python versions/platforms."""

import hashlib

import pytest
from pprl_core.workload import seeded_payload


def test_generator_v1_golden_vector() -> None:
    payload = seeded_payload(42, 0)
    assert len(payload) == 489
    assert hashlib.sha256(payload).hexdigest() == (
        "d596b237e1b4166eed887319eff56c45760f5bee4f9926387cb4fcba17c3a73f"
    )


def test_workload_depends_on_seed_and_repetition() -> None:
    assert seeded_payload(42, 0) == seeded_payload(42, 0)
    assert seeded_payload(42, 0) != seeded_payload(43, 0)
    assert seeded_payload(42, 0) != seeded_payload(42, 1)
    assert 32 <= len(seeded_payload(4294967295, 9)) <= 512


@pytest.mark.parametrize(
    ("seed", "index"),
    [(-1, 0), (4294967296, 0), (True, 0), (0, -1), (0, 10), (0, False)],
)
def test_generator_rejects_invalid_parameters(seed, index) -> None:
    with pytest.raises(ValueError):
        seeded_payload(seed, index)
