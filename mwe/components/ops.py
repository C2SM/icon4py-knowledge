import collections
import functools
from collections.abc import Callable
from datetime import datetime
from typing import Any

import gt4py.next as gtx
import numpy as np
from icon4py.model.common import dimension as dims, type_alias as ta

NCELLS, NEDGES, NLEV = 4, 6, 3
SIZES: dict[gtx.Dimension, int] = {dims.CellDim: NCELLS, dims.EdgeDim: NEDGES, dims.KDim: NLEV, dims.KHalfDim: NLEV + 1}
CELL, CELL_K, EDGE_K = (dims.CellDim,), (dims.CellDim, dims.KDim), (dims.EdgeDim, dims.KDim)
CELL_KHALF = (dims.CellDim, dims.KHalfDim)
DTIME, NDYN_SUBSTEPS, N_STEPS = 1.0, 2, 4
START = datetime(2026, 1, 1)

Array = np.ndarray[Any, Any]
Field = gtx.Field[Any, Any]
CALLS: collections.Counter[str] = collections.Counter()


def counted[**P](f: Callable[P, None]) -> Callable[P, None]:
    @functools.wraps(f)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
        CALLS[f.__name__] += 1
        f(*args, **kwargs)

    return wrapper


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


def copy(f: Field) -> Field:
    g = gtx.zeros(f.domain, dtype=ta.wpfloat)
    arr(g)[...] = arr(f)
    return g


def to_edges(c: Array) -> Array:
    return np.concatenate([c, c[: NEDGES - NCELLS]])


def to_cells(e: Array) -> Array:
    return 0.5 * (e[:NCELLS] + e[NEDGES - NCELLS :])


@counted
def dycore_step(
    *,
    vn_now: Field,
    w_now: Field,
    rho_now: Field,
    exner_now: Field,
    theta_v_now: Field,
    vn_new: Field,
    w_new: Field,
    rho_new: Field,
    exner_new: Field,
    theta_v_new: Field,
    theta_v_ic: Field,
    mass_flx_me: Field,
    predictor_normal_wind_advective_tendency: Field,
    corrector_normal_wind_advective_tendency: Field,
    dtime: float,
    ndyn_substeps: int,
    at_first_substep: bool,
) -> None:
    if at_first_substep:
        arr(mass_flx_me)[...] = 0.0
    arr(mass_flx_me)[...] += arr(vn_now) * to_edges(arr(rho_now)) / ndyn_substeps
    arr(rho_new)[...] = arr(rho_now) - dtime * 0.1 * to_cells(arr(vn_now) * to_edges(arr(rho_now)))
    pressure_gradient = 0.1 * to_edges(arr(theta_v_now)) - 0.01 * arr(vn_now)
    arr(vn_new)[...] = arr(vn_now) + dtime * (pressure_gradient + arr(predictor_normal_wind_advective_tendency))
    compute_advection_in_horizontal_momentum(vn_new, corrector_normal_wind_advective_tendency)
    advection = 0.5 * (arr(predictor_normal_wind_advective_tendency) + arr(corrector_normal_wind_advective_tendency))
    arr(vn_new)[...] = arr(vn_now) + dtime * (pressure_gradient + advection)
    buoyancy = 0.01 * (arr(theta_v_ic)[:, 1:] - arr(theta_v_ic)[:, :-1])
    arr(w_new)[...] = arr(w_now) + dtime * (arr(rho_new) - arr(rho_now) + buoyancy)
    arr(exner_new)[...] = arr(exner_now) * (1.0 + dtime * 0.01 * (arr(rho_new) - arr(rho_now)))
    arr(theta_v_new)[...] = arr(theta_v_now) + dtime * 0.1 * arr(w_new)


@counted
def interpolate_to_half_levels(theta_v: Field, theta_v_ic: Field) -> None:
    arr(theta_v_ic)[:, 0] = arr(theta_v)[:, 0]
    arr(theta_v_ic)[:, 1:NLEV] = 0.5 * (arr(theta_v)[:, :-1] + arr(theta_v)[:, 1:])
    arr(theta_v_ic)[:, NLEV] = arr(theta_v)[:, -1]


@counted
def compute_advection_in_horizontal_momentum(vn: Field, normal_wind_advective_tendency: Field) -> None:
    arr(normal_wind_advective_tendency)[...] = -0.05 * arr(vn) * np.abs(arr(vn))


@counted
def diffuse(vn: Field, theta_v: Field, dtime: float, vn_new: Field, theta_v_new: Field) -> None:
    arr(vn_new)[...] = arr(vn) - dtime * 0.05 * arr(vn)
    arr(theta_v_new)[...] = arr(theta_v) - dtime * 0.05 * arr(theta_v)


@counted
def advect(p_tracer_now: Field, p_tracer_new: Field, mass_flx_me: Field, dtime: float) -> None:
    arr(p_tracer_new)[...] = arr(p_tracer_now) - dtime * 0.1 * to_cells(arr(mass_flx_me)) * arr(p_tracer_now)


@counted
def compute_temperature(theta_v: Field, exner: Field, temperature: Field) -> None:
    arr(temperature)[...] = arr(theta_v) * arr(exner)


@counted
def edge_2_cell_vector_rbf_interpolation(vn: Field, u: Field) -> None:
    arr(u)[...] = to_cells(arr(vn))


@counted
def muphys(te: Field, qv: Field, tend_temperature: Field, tend_qv: Field, pflx: Field) -> None:
    excess = arr(qv) - 0.01 * arr(te)
    arr(tend_qv)[...] = -0.5 * excess
    arr(tend_temperature)[...] = 2.5 * excess
    arr(pflx)[...] = excess.sum(axis=1)


@counted
def tmx(temperature: Field, u: Field, ddt_temperature: Field, ddt_u: Field) -> None:
    arr(ddt_temperature)[...] = 0.1 * (arr(temperature).mean(axis=1, keepdims=True) - arr(temperature))
    arr(ddt_u)[...] = -0.02 * arr(u)


@counted
def update_exner_and_theta_v(
    temperature: Field, exner: Field, theta_v: Field, exner_new: Field, theta_v_new: Field
) -> None:
    arr(exner_new)[...] = arr(exner) * (1.0 + 0.001 * (arr(temperature) - arr(theta_v) * arr(exner)))
    arr(theta_v_new)[...] = arr(temperature) / arr(exner_new)


@counted
def compute_vn_from_uv(u: Field, vn: Field) -> None:
    arr(vn)[...] = to_edges(arr(u))
