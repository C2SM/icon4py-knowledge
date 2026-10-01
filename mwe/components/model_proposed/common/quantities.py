from model_proposed.common import framework as fw


# One tag per quantity; the places it lives at are its nested aliases, so a
# component declares `theta_v: qty.ThetaV.CellK` or `qty.ThetaV.CellKHalf`.
# `standard_name` where the CF table has one (Vn, ThetaV, MassFlux have none).
class Vn(fw.Quantity, units="m s-1"):
    type EdgeK = fw.Field[Vn, fw.EdgeK]


class W(fw.Quantity, standard_name="upward_air_velocity", units="m s-1"):
    type CellK = fw.Field[W, fw.CellK]


class Rho(fw.Quantity, standard_name="air_density", units="kg m-3"):
    type CellK = fw.Field[Rho, fw.CellK]


class Exner(fw.Quantity, standard_name="dimensionless_exner_function", units="1"):
    type CellK = fw.Field[Exner, fw.CellK]


class ThetaV(fw.Quantity, units="K"):
    type CellK = fw.Field[ThetaV, fw.CellK]
    type CellKHalf = fw.Field[ThetaV, fw.CellKHalf]


class Qv(fw.Quantity, standard_name="specific_humidity", units="1"):
    type CellK = fw.Field[Qv, fw.CellK]


class MassFlux(fw.Quantity, units="kg m-2 s-1"):
    type EdgeK = fw.Field[MassFlux, fw.EdgeK]


class Temperature(fw.Quantity, standard_name="air_temperature", units="K"):
    type CellK = fw.Field[Temperature, fw.CellK]


class U(fw.Quantity, standard_name="eastward_wind", units="m s-1", long_name="eastward wind component"):
    type CellK = fw.Field[U, fw.CellK]


class PrecipitationFlux(fw.Quantity, standard_name="precipitation_flux", units="kg m-2 s-1"):
    type Cell = fw.Field[PrecipitationFlux, fw.Cell]

