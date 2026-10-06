import pytest

import run

# the current side computes temperature and u twice per step, for physics and
# for output, and theta_v on half levels once per substep, whatever the config
EXPECTED_CALLS = {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8, "interpolate_to_half_levels": 8}
# the proposed side derives a quantity only on a pass where some component
# declares it: no physics or no output drops a temperature per step, u is
# derived for tmx and for the eastward_wind output only
EXPECTED_PROPOSED_CALLS = {
    "example": {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8, "interpolate_to_half_levels": 8},
    "no_muphys": {"compute_temperature": 8, "edge_2_cell_vector_rbf_interpolation": 8, "interpolate_to_half_levels": 8},
    "no_physics": {"compute_temperature": 4, "edge_2_cell_vector_rbf_interpolation": 0, "interpolate_to_half_levels": 8},
    "no_output": {"compute_temperature": 4, "edge_2_cell_vector_rbf_interpolation": 4, "interpolate_to_half_levels": 8},
    "prognostics": {"compute_temperature": 4, "edge_2_cell_vector_rbf_interpolation": 0, "interpolate_to_half_levels": 8},
}
EXPECTED_PROPOSED_CALLS["dt03"] = EXPECTED_PROPOSED_CALLS["example"]


@pytest.mark.parametrize("label", list(run.RUNS))
def test_current_and_proposed_agree(label: str) -> None:
    run_config, dtime = run.RUNS[label]
    a, b = run.run_current(run_config, dtime), run.run_proposed(run_config, dtime)
    assert run.compare(a, b) == []
    assert a["calls"] == EXPECTED_CALLS
    assert b["calls"] == EXPECTED_PROPOSED_CALLS[label]
