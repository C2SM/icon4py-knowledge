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


class Prognostics(State):
    vn: VnField
    w: WField
    rho: RhoField
    exner: ExnerField
    theta_v: ThetaVField


class Tracers(State):
    qv: QvField


class PrepAdvection(State):
    mass_flux_e: MassFluxField


class Derived(State):
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
