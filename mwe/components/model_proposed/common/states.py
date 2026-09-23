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
    dtime: qty.TimeStep
    substep_dtime: qty.SubstepTimeStep
    ndyn_substeps: qty.SubstepCount
    step_index: qty.StepIndex
    simulation_time: qty.SimulationTime
    at_first_substep: qty.AtFirstSubstep
    at_last_substep: qty.AtLastSubstep
