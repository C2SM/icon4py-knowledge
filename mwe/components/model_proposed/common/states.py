from model_proposed.common.framework import Increment, State
from model_proposed.common.quantities import (
    AtFirstSubstep,
    AtLastSubstep,
    ExnerField,
    MassFluxField,
    QvField,
    RhoField,
    SimulationTime,
    StepIndex,
    SubstepCount,
    SubstepTimeStep,
    TemperatureField,
    ThetaVField,
    TimeStep,
    UField,
    VnField,
    WField,
)


class PrognosticState(State):
    rho: RhoField
    w: WField
    vn: VnField
    exner: ExnerField
    theta_v: ThetaVField


class TracerState(State):
    qv: QvField


class PrepAdvection(State):
    mass_flx_me: MassFluxField


class DiagnosticState(State):
    temperature: TemperatureField
    u: UField


class Increments(State):
    temperature: Increment[TemperatureField]
    qv: Increment[QvField]
    u: Increment[UField]


class StepInfo(State):
    dtime: TimeStep
    substep_dtime: SubstepTimeStep
    ndyn_substeps: SubstepCount
    step_index: StepIndex
    simulation_time: SimulationTime
    at_first_substep: AtFirstSubstep
    at_last_substep: AtLastSubstep
