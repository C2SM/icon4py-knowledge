import pathlib
from typing import Any

import numpy as np

from model_current.driver import driver as current
from model_proposed import driver as proposed
from model_proposed.common import framework as fw
import config
import ops

HERE = pathlib.Path(__file__).parent
COUNTED = ("compute_temperature", "edge_2_cell_vector_rbf_interpolation")
CONFIGS: dict[str, config.Config] = {
    "example": config.load(HERE / "example.yaml"),
    "no_muphys": config.Config(output_variables=("temperature", "eastward_wind"), physics={"tmx": 2}),
    "no_physics": config.Config(output_variables=("temperature",), physics={}),
    "no_output": config.Config(output_variables=(), physics={"muphys": 1, "tmx": 2}),
}


def _calls() -> dict[str, int]:
    return {name: ops.CALLS[name] for name in COUNTED}


def run_current(run_config: config.Config) -> dict[str, Any]:
    ops.CALLS.clear()
    ds, icon4py_driver = current.run_driver(run_config)
    now = ds.prognostics.current
    result = {
        "rho": ops.arr(now.rho),
        "w": ops.arr(now.w),
        "vn": ops.arr(now.vn),
        "exner": ops.arr(now.exner),
        "theta_v": ops.arr(now.theta_v),
        "qv": ops.arr(ds.tracers.current.qv),
        "mass_flx_me": ops.arr(ds.prep_tracer_advection_prognostic.mass_flx_me),
        "ddt_vn_apc.predictor": ops.arr(ds.solve_nonhydro_diagnostic.normal_wind_advective_tendency.predictor),  # type: ignore[arg-type]
        "ddt_vn_apc.corrector": ops.arr(ds.solve_nonhydro_diagnostic.normal_wind_advective_tendency.corrector),  # type: ignore[arg-type]
        "dataset": icon4py_driver.io_monitor.dataset,
        "calls": _calls(),
    }
    if "muphys" in run_config.physics:
        result["pflx"] = ops.arr(icon4py_driver.granules.physics.diagnostics["muphys"]["pflx"])
    return result


def run_proposed(run_config: config.Config) -> dict[str, Any]:
    ops.CALLS.clear()
    icon4py_driver = proposed.Icon4pyDriver(run_config)
    icon4py_driver.time_integration(ops.N_STEPS)
    now = icon4py_driver.prognostic_states.now
    result = {
        "rho": ops.arr(now.rho),
        "w": ops.arr(now.w),
        "vn": ops.arr(now.vn),
        "exner": ops.arr(now.exner),
        "theta_v": ops.arr(now.theta_v),
        "qv": ops.arr(icon4py_driver.tracers.now.qv),
        "mass_flx_me": ops.arr(icon4py_driver.solve_nonhydro.output.mass_flx_me),
        "ddt_vn_apc.predictor": ops.arr(icon4py_driver.solve_nonhydro.normal_wind_advective_tendency.predictor.normal_wind),
        "ddt_vn_apc.corrector": ops.arr(icon4py_driver.solve_nonhydro.normal_wind_advective_tendency.corrector.normal_wind),
        "dataset": icon4py_driver.io_monitor.dataset,
        "calls": _calls(),
    }
    if "muphys" in run_config.physics:
        result["pflx"] = ops.arr(icon4py_driver.physics.processes["muphys"][0].output.pflx)
    return result


def _records_agree(x: tuple[Any, ...], y: tuple[Any, ...]) -> bool:
    if x[:2] != y[:2]:
        return False
    if x[1] == "temperature":
        return bool(np.allclose(x[2], y[2], rtol=1e-12, atol=0.0))
    return bool(np.array_equal(x[2], y[2]))


def compare(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    if a.keys() != b.keys():
        return [f"keys: {sorted(a.keys() ^ b.keys())}"]
    bad = [name for name in a if name not in ("dataset", "calls") and not np.array_equal(a[name], b[name])]
    bad += [
        f"dataset[{i}]"
        for i, (x, y) in enumerate(zip(a["dataset"], b["dataset"], strict=True))
        if not _records_agree(x, y)
    ]
    return bad


def print_dataflow(run_config: config.Config) -> None:
    d = proposed.Icon4pyDriver(run_config)
    p = d.physics
    print(
        fw.dataflow(
            d.solve_nonhydro,
            d.diffusion,
            d.tracer_advection,
            *p.resolution.providers,
            *[process for process, _ in p.processes.values()],
            *p.resolution.write_backs,
            *d.io_resolution.providers,
            d.io_monitor,
        )
    )


if __name__ == "__main__":
    print_dataflow(CONFIGS["example"])
    failed = False
    print(f"\n{'config':<11} {'side':<8} " + " ".join(f"{name:>{len(name)}}" for name in COUNTED))
    for label, run_config in CONFIGS.items():
        a, b = run_current(run_config), run_proposed(run_config)
        mismatches = compare(a, b)
        failed |= bool(mismatches)
        for side, result in (("current", a), ("proposed", b)):
            counts = " ".join(f"{result['calls'][name]:>{len(name)}}" for name in COUNTED)
            verdict = ("OK" if not mismatches else f"MISMATCH {mismatches}") if side == "proposed" else ""
            print(f"{label:<11} {side:<8} {counts}  {verdict}")
    raise SystemExit(1 if failed else 0)
