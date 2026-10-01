import dataclasses
from datetime import datetime

from model_proposed.common import framework as fw, quantities as qty


class PrognosticState(fw.State):
    rho: fw.Field[qty.RhoOnCellK]
    w: fw.Field[qty.WOnCellK]
    vn: fw.Field[qty.VnOnEdgeK]
    exner: fw.Field[qty.ExnerOnCellK]
    theta_v: fw.Field[qty.ThetaVOnCellK]


class TracerState(fw.State):
    qv: fw.Field[qty.QvOnCellK]


class PrepAdvection(fw.State):
    mass_flx_me: fw.Field[qty.MassFluxOnEdgeK]


# the driver's time variables for one step; plain values, not quantities
@dataclasses.dataclass(frozen=True)
class StepInfo:
    dtime: float
    substep_dtime: float
    ndyn_substeps: int
    step_index: int
    simulation_time: datetime
