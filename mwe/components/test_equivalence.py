import pytest

import run

# the current side computes temperature and u twice per step, for physics and
# for output, and theta_v on half levels once per substep; so does this layer
EXPECTED_CALLS = {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8, "interpolate_to_half_levels": 8}
EXPECTED_PROPOSED_CALLS = {label: EXPECTED_CALLS for label in run.CONFIGS}


@pytest.mark.parametrize("label", list(run.CONFIGS))
def test_current_and_proposed_agree(label: str) -> None:
    a, b = run.run_current(run.CONFIGS[label]), run.run_proposed(run.CONFIGS[label])
    assert run.compare(a, b) == []
    assert a["calls"] == EXPECTED_CALLS
    assert b["calls"] == EXPECTED_PROPOSED_CALLS[label]
