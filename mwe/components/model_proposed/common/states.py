import dataclasses
from datetime import datetime

from model_proposed.common import framework as fw, quantities as qty


class PrognosticState(fw.State):
    rho: qty.Rho.CellK
    w: qty.W.CellK
    vn: qty.Vn.EdgeK
    exner: qty.Exner.CellK
    theta_v: qty.ThetaV.CellK


class TracerState(fw.State):
    qv: qty.Qv.CellK


class PrepAdvection(fw.State):
    mass_flx_me: qty.MassFlux.EdgeK


# the driver's time variables for one step; plain values, not quantities
@dataclasses.dataclass(frozen=True)
class StepInfo:
    dtime: float
    substep_dtime: float
    ndyn_substeps: int
    step_index: int
    simulation_time: datetime
