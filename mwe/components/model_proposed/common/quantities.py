from datetime import datetime

from model_proposed.common import framework as fw

# Quantities as phantom types
class Vn(fw.Quantity, locations=(fw.EdgeK,), units="m s-1"): ...
class W(fw.Quantity, locations=(fw.CellK,), standard_name="upward_air_velocity", units="m s-1"): ...
class Rho(fw.Quantity, locations=(fw.CellK,), standard_name="air_density", units="kg m-3"): ...
class Exner(fw.Quantity, locations=(fw.CellK,), standard_name="dimensionless_exner_function", units="1"): ...
class ThetaV(fw.Quantity, locations=(fw.CellK, fw.CellKHalf), units="K"): ...
class Qv(fw.Quantity, locations=(fw.CellK,), standard_name="specific_humidity", units="1"): ...
class MassFlux(fw.Quantity, locations=(fw.EdgeK,), units="kg m-2 s-1"): ...
class Temperature(fw.Quantity, locations=(fw.CellK,), standard_name="air_temperature", units="K"): ...
class U(fw.Quantity, locations=(fw.CellK,), standard_name="eastward_wind", units="m s-1", long_name="eastward wind component"): ...
class PrecipitationFlux(fw.Quantity, locations=(fw.Cell,), standard_name="precipitation_flux", units="kg m-2 s-1"): ...

# Quantities at a grid location cannot yet be phantom types because of the
# GT4Py static caveat explained below
type VnField = fw.EdgeK[Vn]
type WField = fw.CellK[W]
type RhoField = fw.CellK[Rho]
type ExnerField = fw.CellK[Exner]
type ThetaVField = fw.CellK[ThetaV]
type ThetaVAtCellsOnHalfLevelsField = fw.CellKHalf[ThetaV]
type QvField = fw.CellK[Qv]
type MassFluxField = fw.EdgeK[MassFlux]
type TemperatureField = fw.CellK[Temperature]
type UField = fw.CellK[U]
type PrecipitationFluxField = fw.Cell[PrecipitationFlux]

# Relocations between a quantity's grid locations are recipes decorated with
# `fw.relocation` (recipes.ThetaVToHalfLevels), and a consumer uses one
# explicitly:
# `theta_v_ic: ThetaVAtCellsOnHalfLevelsField = derived_by(ThetaVToHalfLevels)`.
# Option kept for later: a family-level lookup, where a leaf declared at a
# location nobody supplies and with no `derived_by` is served by the recipe
# `fw.RELOCATIONS[(quantity, supplied location, wanted location)]`; direct
# edges only, error when two supplied locations both have one, `derived_by`
# still overrides.
# Static caveat: to mypy and pyright `fw.CellKHalf[ThetaV]` is
# `Field[Dims[Unknown, Unknown], wpfloat]` (dims are runtime objects), so a
# location mismatch is caught by the framework at init, not by the checker; an
# undeclared location (`locations=`) is caught at import.


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
