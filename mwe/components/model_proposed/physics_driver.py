import dataclasses
from typing import Any

from model_proposed.common.framework import Component, Empty, Read, ReadWrite, State, allocate, zero
from model_proposed.common.quantities import (
    ExnerField,
    QvField,
    RhoField,
    StepIndex,
    ThetaVField,
    TimeStep,
    VnField,
    WField,
)
from model_proposed.common.states import Derived, Increments
from model_proposed.derived import DerivedQuantities
from model_proposed.eos import ExnerThetaUpdate
from model_proposed.muphys import Muphys
from model_proposed.projection import WindProjection
from model_proposed.tmx import Tmx
import ops


@dataclasses.dataclass(frozen=True)
class Every:
    steps: int

    def due(self, step: int) -> bool:
        return step % self.steps == 0


class Physics(Component["Physics.Input", Empty]):
    class Input(State):
        vn: ReadWrite[VnField]
        w: Read[WField]
        rho: Read[RhoField]
        exner: ReadWrite[ExnerField]
        theta_v: ReadWrite[ThetaVField]
        qv: ReadWrite[QvField]
        dtime: Read[TimeStep]
        step_index: Read[StepIndex]

    Output = Empty

    def __init__(self) -> None:
        super().__init__(Empty())
        self.derived = DerivedQuantities(allocate(Derived, ops.SIZES))
        self.muphys = Muphys(allocate(Muphys.Output, ops.SIZES))
        self.tmx = Tmx(allocate(Tmx.Output, ops.SIZES))
        self.processes: list[tuple[Component[Any, Any], Every]] = [
            (self.muphys, Every(1)),
            (self.tmx, Every(ops.TMX_INTERVAL)),
        ]
        self.increments = allocate(Increments, ops.SIZES)
        self.eos = ExnerThetaUpdate(Empty())
        self.projection = WindProjection(Empty())

    def run(self, input: Input) -> Empty:
        derived = self.derived.run(self.derived.gather(input))
        zero(self.increments)
        for process, cadence in self.processes:
            if cadence.due(input.step_index):
                process.run(process.gather(input, derived))
            process.accumulate(self.increments, input.dtime)
        self.apply(self.increments, input, derived)
        self.eos.run(self.eos.gather(input, derived))
        self.projection.run(self.projection.gather(input, derived))
        return self.output
