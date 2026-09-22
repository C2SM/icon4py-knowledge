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
from model_proposed.common.states import DiagnosticState, Increments
from model_proposed.diagnostics import DiagnosticsComputer
from model_proposed.eos import ExnerThetaUpdate
from model_proposed.muphys import MuphysComponent
from model_proposed.projection import WindProjection
from model_proposed.tmx import TmxComponent
import ops


@dataclasses.dataclass(frozen=True)
class ProcessTimeControl:
    interval: int

    def is_active(self, step_index: int) -> bool:
        return step_index % self.interval == 0


class PhysicsDriver(Component["PhysicsDriver.Input", Empty]):
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
        self.entry = DiagnosticsComputer(allocate(DiagnosticState, ops.SIZES))
        self.muphys = MuphysComponent(allocate(MuphysComponent.Output, ops.SIZES))
        self.tmx = TmxComponent(allocate(TmxComponent.Output, ops.SIZES))
        self.processes: list[tuple[Component[Any, Any], ProcessTimeControl]] = [
            (self.muphys, ProcessTimeControl(1)),
            (self.tmx, ProcessTimeControl(ops.TMX_INTERVAL)),
        ]
        self.increments = allocate(Increments, ops.SIZES)
        self.eos = ExnerThetaUpdate(Empty())
        self.projection = WindProjection(Empty())

    def run(self, input: Input) -> Empty:
        entry = self.entry.run(self.entry.collect_inputs(input))
        zero(self.increments)
        for process, time_control in self.processes:
            if time_control.is_active(input.step_index):
                process.run(process.collect_inputs(input, entry))
            process.accumulate(self.increments, input.dtime)
        self.apply(self.increments, input)
        self.eos.run(self.eos.collect_inputs(entry, self.increments, input))
        self.projection.run(self.projection.collect_inputs(self.increments, input))
        return self.output
