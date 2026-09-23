from typing import Any

import numpy as np

from model_current.driver import driver as current
from model_proposed import driver as proposed
from model_proposed.common import framework as fw
import ops


def run_current() -> dict[str, Any]:
    ds, icon4py_driver = current.run_driver()
    now = ds.prognostics.current
    return {
        "rho": ops.arr(now.rho),
        "w": ops.arr(now.w),
        "vn": ops.arr(now.vn),
        "exner": ops.arr(now.exner),
        "theta_v": ops.arr(now.theta_v),
        "qv": ops.arr(ds.tracers.current.qv),
        "mass_flx_me": ops.arr(ds.prep_tracer_advection_prognostic.mass_flx_me),
        "pflx": ops.arr(icon4py_driver.granules.physics.diagnostics["muphys"]["pflx"]),
        "ddt_vn_apc.predictor": ops.arr(ds.solve_nonhydro_diagnostic.normal_wind_advective_tendency.predictor),  # type: ignore[arg-type]
        "ddt_vn_apc.corrector": ops.arr(ds.solve_nonhydro_diagnostic.normal_wind_advective_tendency.corrector),  # type: ignore[arg-type]
        "dataset": icon4py_driver.io_monitor.dataset,
    }


def run_proposed() -> dict[str, Any]:
    icon4py_driver = proposed.Icon4pyDriver()
    icon4py_driver.time_integration(ops.N_STEPS)
    now = icon4py_driver.prognostic_states.now
    return {
        "rho": ops.arr(now.rho),
        "w": ops.arr(now.w),
        "vn": ops.arr(now.vn),
        "exner": ops.arr(now.exner),
        "theta_v": ops.arr(now.theta_v),
        "qv": ops.arr(icon4py_driver.tracers.now.qv),
        "mass_flx_me": ops.arr(icon4py_driver.solve_nonhydro.output.mass_flx_me),
        "pflx": ops.arr(icon4py_driver.physics.muphys.output.pflx),
        "ddt_vn_apc.predictor": ops.arr(icon4py_driver.solve_nonhydro.normal_wind_advective_tendency.predictor.normal_wind),
        "ddt_vn_apc.corrector": ops.arr(icon4py_driver.solve_nonhydro.normal_wind_advective_tendency.corrector.normal_wind),
        "dataset": icon4py_driver.io_monitor.dataset,
    }


def compare(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    bad = [name for name in a if name != "dataset" and not np.array_equal(a[name], b[name])]
    bad += [
        f"dataset[{i}]"
        for i, (x, y) in enumerate(zip(a["dataset"], b["dataset"], strict=True))
        if x[:2] != y[:2] or not np.array_equal(x[2], y[2])
    ]
    return bad


if __name__ == "__main__":
    d = proposed.Icon4pyDriver()
    p = d.physics
    print(
        fw.dataflow(
            d.solve_nonhydro,
            d.diffusion,
            d.tracer_advection,
            p.entry,
            p.muphys,
            p.tmx,
            p.eos,
            p.projection,
            d.diagnostics_computer,
            d.io_monitor,
        )
    )
    mismatches = compare(run_current(), run_proposed())
    print("OK" if not mismatches else f"MISMATCH: {mismatches}")
    raise SystemExit(1 if mismatches else 0)
