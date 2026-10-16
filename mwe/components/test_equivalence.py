import pytest

import run

# the current side computes temperature and u twice per step, for physics and
# for output, and theta_v on half levels once per substep, whatever the config
EXPECTED_CALLS = {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8, "interpolate_to_half_levels": 8}
# the proposed side derives a quantity on a pass only when a component in it
# declares it: no physics drops that pass's temperature and u, muphys alone
# never asks for u; IO declares both diagnostics whatever the config asks
EXPECTED_PROPOSED_CALLS = {
    "example": {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8, "interpolate_to_half_levels": 8},
    "no_muphys": {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8, "interpolate_to_half_levels": 8},
    "no_physics": {"compute_temperature": 4, "edge_2_cell_vector_rbf_interpolation": 4, "interpolate_to_half_levels": 8},
    "no_output": {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8, "interpolate_to_half_levels": 8},
    "prognostics": {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 4, "interpolate_to_half_levels": 8},
}


@pytest.mark.parametrize("label", list(run.CONFIGS))
def test_current_and_proposed_agree(label: str) -> None:
    a, b = run.run_current(run.CONFIGS[label]), run.run_proposed(run.CONFIGS[label])
    assert run.compare(a, b) == []
    assert a["calls"] == EXPECTED_CALLS
    assert b["calls"] == EXPECTED_PROPOSED_CALLS[label]
