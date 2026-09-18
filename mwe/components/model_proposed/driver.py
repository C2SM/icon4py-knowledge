import dataclasses
from datetime import timedelta
from typing import Any

from model_proposed.advection import Advection
from model_proposed.common.framework import Empty, Pair, allocate
from model_proposed.common.states import PrepAdvection, Prognostics, StepInfo, Tracers
from model_proposed.diffusion import Diffusion
from model_proposed.dycore import Dycore
from model_proposed.io import Writer
from model_proposed.physics_driver import Physics
import ops


class TimeLoop:
    def __init__(self) -> None:
        self.prognostics = Pair(allocate(Prognostics, ops.SIZES, ops.initial), allocate(Prognostics, ops.SIZES))
        self.tracers = Pair(allocate(Tracers, ops.SIZES, ops.initial), allocate(Tracers, ops.SIZES))
        self.dycore = Dycore(allocate(PrepAdvection, ops.SIZES))
        self.diffusion = Diffusion(Empty())
        self.advection = Advection(Empty())
        self.physics = Physics()
        self.writer = Writer()

    def run(self, n_steps: int) -> None:
        for step in range(n_steps):
            self._time_step(step)

    def _time_step(self, step: int) -> None:
        info = StepInfo(
            dtime=ops.DTIME,
            substep_dtime=ops.DTIME / ops.NDYN_SUBSTEPS,
            ndyn_substeps=ops.NDYN_SUBSTEPS,
            step_index=step,
            simulation_time=ops.START + timedelta(seconds=(step + 1) * ops.DTIME),
            at_first_substep=False,
            at_last_substep=False,
        )
        for substep in range(ops.NDYN_SUBSTEPS):
            sub = dataclasses.replace(
                info, at_first_substep=substep == 0, at_last_substep=substep == ops.NDYN_SUBSTEPS - 1
            )
            self.dycore.run(self.dycore.gather(self.prognostics, sub))
            if not sub.at_last_substep:
                self.prognostics.swap()
        self.diffusion.run(self.diffusion.gather(self.prognostics.next, info))
        self.advection.run(self.advection.gather(self.tracers, self.dycore.output, info))
        self.physics.run(self.physics.gather(self.prognostics.next, self.tracers.next, info))
        self.writer.run(self.writer.gather(self.physics.derived.output, self.physics.muphys.output, info))
        self.prognostics.swap()
        self.tracers.swap()

    def results(self) -> dict[str, Any]:
        now, derived = self.prognostics.now, self.physics.derived.output
        return {
            "vn": ops.arr(now.vn),
            "w": ops.arr(now.w),
            "rho": ops.arr(now.rho),
            "exner": ops.arr(now.exner),
            "theta_v": ops.arr(now.theta_v),
            "qv": ops.arr(self.tracers.now.qv),
            "mass_flux_e": ops.arr(self.dycore.output.mass_flux_e),
            "temperature": ops.arr(derived.temperature),
            "u": ops.arr(derived.u),
            "precip": ops.arr(self.physics.muphys.output.precip),
            "records": self.writer.records,
        }
