from datetime import datetime
from typing import Annotated

from icon4py.model.common import field_type_aliases as fa, type_alias as ta

from model_proposed.common import framework as fw

type VnField = Annotated[fa.EdgeKField[ta.wpfloat], fw.quantity("normal_velocity", units="m s-1", cf_key="vn")]
type WField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("upward_air_velocity", units="m s-1", cf_key="w")]
type RhoField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("air_density", units="kg m-3", cf_key="rho")]
type ExnerField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("dimensionless_exner_function", units="1", cf_key="exner")]
type ThetaVField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("virtual_potential_temperature", units="K", cf_key="theta_v")]
type QvField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("specific_humidity", units="1", cf_key="qv")]
type MassFluxField = Annotated[fa.EdgeKField[ta.wpfloat], fw.quantity("mass_flux_at_edges", units="kg m-2 s-1")]
type TemperatureField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("air_temperature", units="K", cf_key="temperature")]
type UField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("eastward_wind", units="m s-1", cf_key="u")]
type PrecipField = Annotated[fa.CellField[ta.wpfloat], fw.quantity("precipitation_flux", units="kg m-2 s-1")]

type TimeStep = Annotated[float, fw.quantity("time_step", units="s")]
type SubstepTimeStep = Annotated[float, fw.quantity("dynamics_substep", units="s")]
type SubstepCount = Annotated[int, fw.quantity("dynamics_substep_count", units="1")]
type StepIndex = Annotated[int, fw.quantity("step_index", units="1")]
type SimulationTime = Annotated[datetime, fw.quantity("simulation_time", units="1")]
type AtFirstSubstep = Annotated[bool, fw.quantity("at_first_substep", units="1")]
type AtLastSubstep = Annotated[bool, fw.quantity("at_last_substep", units="1")]
