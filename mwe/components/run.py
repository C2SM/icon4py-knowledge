import dataclasses
import pathlib
from typing import Any, cast

import numpy as np

from model_current.common.states import data as state_data
from model_current.driver import driver as current
from model_proposed import (
    diffusion,
    driver as proposed,
    physics_driver,
    recipes,
    solve_nonhydro,
    tracer_advection,
)
from model_proposed.common import framework as fw
import config
import ops

HERE = pathlib.Path(__file__).parent
COUNTED = ("compute_temperature", "edge_2_cell_vector_rbf_interpolation", "interpolate_to_half_levels")
CONFIGS: dict[str, config.Config] = {
    "example": config.load(HERE / "example.yaml"),
    "no_muphys": config.Config(output_variables=("air_temperature", "eastward_wind"), physics={"tmx": 2}),
    "no_physics": config.Config(output_variables=("air_temperature",), physics={}),
    "no_output": config.Config(output_variables=(), physics={"muphys": 1, "tmx": 2}),
    "prognostics": config.Config(output_variables=("Vn", "air_density"), physics={"muphys": 1}),
}


# the config names output variables by CF standard name, or by the quantity's
# class name where the CF table has none; model_current names them by its own
# dict keys, so the harness translates on the way in and out
ICON_KEY: dict[str, str] = {
    meta.standard_name: key
    for table in (state_data.PROGNOSTIC_CF_ATTRIBUTES, state_data.DIAGNOSTIC_CF_ATTRIBUTES)
    for key, meta in table.items()
} | {"Vn": "normal_velocity", "ThetaV": "virtual_potential_temperature"}
STANDARD_NAME: dict[str, str] = {key: name for name, key in ICON_KEY.items()}


def _calls() -> dict[str, int]:
    return {name: ops.CALLS[name] for name in COUNTED}


def run_current(run_config: config.Config) -> dict[str, Any]:
    ops.CALLS.clear()
    legacy_config = dataclasses.replace(
        run_config, output_variables=tuple(ICON_KEY[name] for name in run_config.output_variables)
    )
    ds, icon4py_driver = current.run_driver(legacy_config)
    now = ds.prognostics.current
    result = {
        "rho": ops.arr(now.rho),
        "w": ops.arr(now.w),
        "vn": ops.arr(now.vn),
        "exner": ops.arr(now.exner),
        "theta_v": ops.arr(now.theta_v),
        "qv": ops.arr(ds.tracers.current.qv),
        "mass_flx_me": ops.arr(ds.prep_tracer_advection_prognostic.mass_flx_me),
        "ddt_vn_apc.predictor": ops.arr(cast(ops.Field, ds.solve_nonhydro_diagnostic.normal_wind_advective_tendency.predictor)),
        "ddt_vn_apc.corrector": ops.arr(cast(ops.Field, ds.solve_nonhydro_diagnostic.normal_wind_advective_tendency.corrector)),
        "dataset": [(time, STANDARD_NAME[key], array) for time, key, array in icon4py_driver.io_monitor.dataset],
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
    pair = icon4py_driver.solve_nonhydro.normal_wind_advective_tendency
    result = {
        "rho": ops.arr(now.rho.data),
        "w": ops.arr(now.w.data),
        "vn": ops.arr(now.vn.data),
        "exner": ops.arr(now.exner.data),
        "theta_v": ops.arr(now.theta_v.data),
        "qv": ops.arr(icon4py_driver.tracers.now.qv.data),
        "mass_flx_me": ops.arr(icon4py_driver.prep_advection.mass_flx_me.data),
        "ddt_vn_apc.predictor": ops.arr(pair.predictor.normal_wind.data),
        "ddt_vn_apc.corrector": ops.arr(pair.corrector.normal_wind.data),
        "dataset": icon4py_driver.io_monitor.dataset,
        "calls": _calls(),
    }
    if "muphys" in run_config.physics:
        result["pflx"] = ops.arr(getattr(icon4py_driver.physics.outputs["muphys"], "pflx").data)
    return result


# the declared dataflow of the proposed model, in the order the driver runs it
def print_dataflow(run_config: config.Config) -> None:
    icon4py_driver = proposed.Icon4pyDriver(run_config)
    print(
        fw.dataflow(
            *icon4py_driver.dycore_resolution.providers,
            solve_nonhydro.SolveNonhydro,
            diffusion.Diffusion,
            tracer_advection.Advection,
            *icon4py_driver.physics.resolution.providers,
            *[physics_driver.PROCESSES[name] for name in run_config.physics],
            recipes.VnTendencyFromUTendency,
            recipes.ExnerThetaFromTemperature,
            physics_driver.PhysicsDriver,
            *icon4py_driver.io_resolution.providers,
            icon4py_driver.io_monitor,
        )
    )


def _records_agree(x: tuple[Any, ...], y: tuple[Any, ...]) -> bool:
    return x[:2] == y[:2] and bool(np.array_equal(x[2], y[2]))


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
