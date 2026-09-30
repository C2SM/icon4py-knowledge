from datetime import datetime

from model_proposed.common import framework as fw


class Vn(fw.Quantity, units="m s-1", locations=(fw.EdgeK,)): ...
class W(fw.Quantity, units="m s-1", standard_name="upward_air_velocity", locations=(fw.CellK,)): ...
class Rho(fw.Quantity, units="kg m-3", standard_name="air_density", locations=(fw.CellK,)): ...
class Exner(fw.Quantity, units="1", standard_name="dimensionless_exner_function", locations=(fw.CellK,)): ...
class ThetaV(fw.Quantity, units="K", locations=(fw.CellK, fw.CellKHalf)): ...
class Qv(fw.Quantity, units="1", standard_name="specific_humidity", locations=(fw.CellK,)): ...
class MassFlux(fw.Quantity, units="kg m-2 s-1", locations=(fw.EdgeK,)): ...
class Temperature(fw.Quantity, units="K", standard_name="air_temperature", locations=(fw.CellK,)): ...
class U(fw.Quantity, units="m s-1", standard_name="eastward_wind", long_name="eastward wind component", locations=(fw.CellK,)): ...
class PrecipitationFlux(fw.Quantity, units="kg m-2 s-1", standard_name="precipitation_flux", locations=(fw.Cell,)): ...

type VnField = fw.EdgeK[Vn]
type WField = fw.CellK[W]
type RhoField = fw.CellK[Rho]
type ExnerField = fw.CellK[Exner]
type ThetaVField = fw.CellK[ThetaV]
type ThetaVAtCellsOnHalfLevels = fw.CellKHalf[ThetaV]
type QvField = fw.CellK[Qv]
type MassFluxField = fw.EdgeK[MassFlux]
type TemperatureField = fw.CellK[Temperature]
type UField = fw.CellK[U]
type PrecipitationFluxField = fw.Cell[PrecipitationFlux]

# Relocations between a quantity's grid locations are recipes decorated with
# `fw.relocation` (recipes.ThetaVToHalfLevels), and a consumer uses one
# explicitly:
# `theta_v_ic: ThetaVAtCellsOnHalfLevels = derived_by(ThetaVToHalfLevels)`.
# Option kept for later: a family-level lookup, where a leaf declared at a
# location nobody supplies and with no `derived_by` is served by the recipe
# `fw.RELOCATIONS[(quantity, supplied location, wanted location)]`; direct
# edges only, error when two supplied locations both have one, `derived_by`
# still overrides. Static caveat: to mypy and pyright `fw.CellKHalf[ThetaV]` is
# `Field[Dims[Unknown, Unknown], wpfloat]` (dims are runtime objects), so a
# location mismatch is caught by the framework at init, not by the checker;
# an undeclared location (`locations=`) is caught at import.


class TimeStep(fw.Quantity, units="s"): ...
class SubstepTimeStep(fw.Quantity, units="s"): ...
class SubstepCount(fw.Quantity, units="1"): ...
class StepIndex(fw.Quantity, units="1"): ...
class SimulationTime(fw.Quantity, units="1"): ...
class AtFirstSubstep(fw.Quantity, units="1"): ...
class AtLastSubstep(fw.Quantity, units="1"): ...

type TimeStepValue = fw.Scalar[float, TimeStep]
type SubstepTimeStepValue = fw.Scalar[float, SubstepTimeStep]
type SubstepCountValue = fw.Scalar[int, SubstepCount]
type StepIndexValue = fw.Scalar[int, StepIndex]
type SimulationTimeValue = fw.Scalar[datetime, SimulationTime]
type AtFirstSubstepValue = fw.Scalar[bool, AtFirstSubstep]
type AtLastSubstepValue = fw.Scalar[bool, AtLastSubstep]
