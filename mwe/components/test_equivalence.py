import pytest

import run

EXPECTED_PROPOSED_CALLS = {
    "example": {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8},
    "no_muphys": {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8},
    "no_physics": {"compute_temperature": 4, "edge_2_cell_vector_rbf_interpolation": 0},
    "no_output": {"compute_temperature": 4, "edge_2_cell_vector_rbf_interpolation": 4},
}


@pytest.mark.parametrize("label", list(run.CONFIGS))
def test_current_and_proposed_agree(label: str) -> None:
    a, b = run.run_current(run.CONFIGS[label]), run.run_proposed(run.CONFIGS[label])
    assert run.compare(a, b) == []
    assert b["calls"] == EXPECTED_PROPOSED_CALLS[label]
    assert a["calls"] == {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8}
