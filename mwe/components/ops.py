from datetime import datetime
from typing import Any

import gt4py.next as gtx
import numpy as np
from icon4py.model.common import dimension as dims, type_alias as ta

NCELLS, NEDGES, NLEV = 4, 6, 3
SIZES: dict[gtx.Dimension, int] = {dims.CellDim: NCELLS, dims.EdgeDim: NEDGES, dims.KDim: NLEV}
DTIME, NDYN_SUBSTEPS, N_STEPS, TMX_INTERVAL = 1.0, 2, 4, 2
START = datetime(2026, 1, 1)

Array = np.ndarray[Any, Any]
Field = gtx.Field[Any, Any]


def arr(f: Field) -> Array:
    return np.asarray(f.ndarray)


def initial(name: str, shape: tuple[int, ...]) -> Array:
    seed = 1 + sum(map(ord, name)) % 7
    return 1.0 + 0.01 * seed * np.arange(np.prod(shape), dtype=np.float64).reshape(shape)


def field(dimensions: tuple[gtx.Dimension, ...], name: str | None = None) -> Field:
    f = gtx.zeros({d: SIZES[d] for d in dimensions}, dtype=ta.wpfloat)
    if name is not None:
        arr(f)[...] = initial(name, arr(f).shape)
    return f


def to_edges(c: Array) -> Array:
    return np.concatenate([c, c[: NEDGES - NCELLS]])


def to_cells(e: Array) -> Array:
    return 0.5 * (e[:NCELLS] + e[NEDGES - NCELLS :])


def dycore_step(
    *,
    vn: Field,
    w: Field,
    rho: Field,
    exner: Field,
    theta_v: Field,
    vn_new: Field,
    w_new: Field,
    rho_new: Field,
    exner_new: Field,
    theta_v_new: Field,
    mass_flux_e: Field,
    dt: float,
    ndyn_substeps: int,
    at_first_substep: bool,
) -> None:
    if at_first_substep:
        arr(mass_flux_e)[...] = 0.0
    arr(mass_flux_e)[...] += arr(vn) * to_edges(arr(rho)) / ndyn_substeps
    arr(rho_new)[...] = arr(rho) - dt * 0.1 * to_cells(arr(vn) * to_edges(arr(rho)))
    arr(vn_new)[...] = arr(vn) + dt * (0.1 * to_edges(arr(theta_v)) - 0.01 * arr(vn))
    arr(w_new)[...] = arr(w) + dt * (arr(rho_new) - arr(rho))
    arr(exner_new)[...] = arr(exner) * (1.0 + dt * 0.01 * (arr(rho_new) - arr(rho)))
    arr(theta_v_new)[...] = arr(theta_v) + dt * 0.1 * arr(w_new)


def diffuse(vn: Field, theta_v: Field, dt: float) -> None:
    arr(vn)[...] -= dt * 0.05 * arr(vn)
    arr(theta_v)[...] -= dt * 0.05 * arr(theta_v)


def advect(qv_now: Field, qv_new: Field, mass_flux_e: Field, dt: float) -> None:
    arr(qv_new)[...] = arr(qv_now) - dt * 0.1 * to_cells(arr(mass_flux_e)) * arr(qv_now)


def diagnose(exner: Field, theta_v: Field, vn: Field, temperature: Field, u: Field) -> None:
    arr(temperature)[...] = arr(theta_v) * arr(exner)
    arr(u)[...] = to_cells(arr(vn))


def muphys(temperature: Field, qv: Field, ddt_temperature: Field, ddt_qv: Field, precip: Field) -> None:
    excess = arr(qv) - 0.01 * arr(temperature)
    arr(ddt_qv)[...] = -0.5 * excess
    arr(ddt_temperature)[...] = 2.5 * excess
    arr(precip)[...] = excess.sum(axis=1)


def tmx(temperature: Field, u: Field, ddt_temperature: Field, ddt_u: Field) -> None:
    arr(ddt_temperature)[...] = 0.1 * (arr(temperature).mean(axis=1, keepdims=True) - arr(temperature))
    arr(ddt_u)[...] = -0.02 * arr(u)


def eos(temperature: Field, exner: Field, theta_v: Field) -> None:
    arr(exner)[...] *= 1.0 + 0.001 * (arr(temperature) - arr(theta_v) * arr(exner))
    arr(theta_v)[...] = arr(temperature) / arr(exner)


def project(u: Field, vn: Field) -> None:
    arr(vn)[...] += 0.5 * (to_edges(arr(u)) - to_edges(to_cells(arr(vn))))
