from model_proposed.common import framework as fw, quantities as qty


class PrognosticState(fw.State):
    rho: qty.RhoField
    w: qty.WField
    vn: qty.VnField
    exner: qty.ExnerField
    theta_v: qty.ThetaVField


class TracerState(fw.State):
    qv: qty.QvField


class PrepAdvection(fw.State):
    mass_flx_me: qty.MassFluxField


class StepInfo(fw.State):
    dtime: qty.TimeStepValue
    substep_dtime: qty.SubstepTimeStepValue
    ndyn_substeps: qty.SubstepCountValue
    step_index: qty.StepIndexValue
    simulation_time: qty.SimulationTimeValue
    at_first_substep: qty.AtFirstSubstepValue
    at_last_substep: qty.AtLastSubstepValue
