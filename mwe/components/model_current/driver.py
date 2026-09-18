from datetime import timedelta
from typing import Any

import gt4py.next as gtx
from icon4py.model.common import dimension as dims
from model_current.advection import Advection
from model_current.common.states import PrepAdvection, PrognosticState, TimeStepPair, TracerState
from model_current.diffusion import Diffusion
from model_current.dycore import SolveNonhydro
from model_current.io import OutputWriter
from model_current.muphys import MuphysComponent, MuphysState
from model_current.physics_driver import (
    ApplyToPrognostic,
    DiagnosticsStore,
    EntryState,
    PhysicsDriver,
    PhysicsProcess,
    ProcessTimeControl,
    TendencyAccumulators,
)
from model_current.tmx import TmxComponent, TmxState
import ops

CELL_K, EDGE_K = (dims.CellDim, dims.KDim), (dims.EdgeDim, dims.KDim)


def prognostic_state(seeded: bool) -> PrognosticState:
    def f(dimensions: tuple[gtx.Dimension, ...], name: str) -> ops.Field:
        return ops.field(dimensions, name if seeded else None)

    return PrognosticState(
        vn=f(EDGE_K, "vn"), w=f(CELL_K, "w"), rho=f(CELL_K, "rho"), exner=f(CELL_K, "exner"), theta_v=f(CELL_K, "theta_v")
    )


class TimeLoop:
    def __init__(self) -> None:
        self.prognostic_states = TimeStepPair(prognostic_state(True), prognostic_state(False))
        self.tracers = TimeStepPair(TracerState(qv=ops.field(CELL_K, "qv")), TracerState(qv=ops.field(CELL_K)))
        self.prep_adv = PrepAdvection(mass_flux_e=ops.field(EDGE_K))
        self.solve_nonhydro, self.diffusion, self.advection = SolveNonhydro(), Diffusion(), Advection()
        self.physics = PhysicsDriver(
            processes=[
                PhysicsProcess("muphys", MuphysComponent(), MuphysState(), ProcessTimeControl(1)),
                PhysicsProcess("tmx", TmxComponent(), TmxState(), ProcessTimeControl(ops.TMX_INTERVAL)),
            ],
            entry_state=EntryState(),
            accumulators=TendencyAccumulators(),
            apply_to_prognostic=ApplyToPrognostic(),
            diagnostics=DiagnosticsStore(),
        )
        self.writer = OutputWriter()

    def run(self, n_steps: int) -> None:
        for step in range(n_steps):
            self._time_step(step)

    def _time_step(self, step: int) -> None:
        simulation_time = ops.START + timedelta(seconds=(step + 1) * ops.DTIME)
        for substep in range(ops.NDYN_SUBSTEPS):
            self.solve_nonhydro.time_step(
                self.prognostic_states,
                self.prep_adv,
                ops.DTIME / ops.NDYN_SUBSTEPS,
                ops.NDYN_SUBSTEPS,
                substep == 0,
                substep == ops.NDYN_SUBSTEPS - 1,
            )
            if substep != ops.NDYN_SUBSTEPS - 1:
                self.prognostic_states.swap()
        self.diffusion.run(self.prognostic_states.next, ops.DTIME)
        self.advection.run(self.prep_adv, self.tracers.current.qv, self.tracers.next.qv, ops.DTIME)
        self.physics.run(self.prognostic_states.next, self.tracers.next, ops.DTIME, step, simulation_time)
        self.writer.write(
            simulation_time,
            {
                "temperature": self.physics.entry.temperature,
                "pflx": self.physics.diagnostics["muphys"]["pflx"],
                "tend_temperature_muphys": self.physics.recycle_cache["muphys"]["tend_temperature"],
            },
        )
        self.prognostic_states.swap()
        self.tracers.swap()

    def results(self) -> dict[str, Any]:
        now, entry = self.prognostic_states.current, self.physics.entry
        return {
            "vn": ops.arr(now.vn),
            "w": ops.arr(now.w),
            "rho": ops.arr(now.rho),
            "exner": ops.arr(now.exner),
            "theta_v": ops.arr(now.theta_v),
            "qv": ops.arr(self.tracers.current.qv),
            "mass_flux_e": ops.arr(self.prep_adv.mass_flux_e),
            "temperature": ops.arr(entry.temperature),
            "u": ops.arr(entry.u),
            "precip": ops.arr(self.physics.diagnostics["muphys"]["pflx"]),
            "records": self.writer.records,
        }
