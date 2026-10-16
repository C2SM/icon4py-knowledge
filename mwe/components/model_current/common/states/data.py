from typing import Final

from model_current.common.states import model

PROGNOSTIC_CF_ATTRIBUTES: Final[dict[str, model.FieldMetaData]] = dict(
    air_density=model.FieldMetaData(standard_name="air_density", units="kg m-3", icon_var_name="rho"),
    virtual_potential_temperature=model.FieldMetaData(
        standard_name="virtual_potential_temperature", units="K", icon_var_name="theta_v"
    ),
    exner_function=model.FieldMetaData(standard_name="dimensionless_exner_function", units="1", icon_var_name="exner"),
    upward_air_velocity=model.FieldMetaData(standard_name="upward_air_velocity", units="m s-1", icon_var_name="w"),
    normal_velocity=model.FieldMetaData(standard_name="normal_velocity", units="m s-1", icon_var_name="vn"),
)
COMMON_TRACER_CF_ATTRIBUTES: Final[dict[str, model.FieldMetaData]] = dict(
    qv=model.FieldMetaData(standard_name="specific_humidity", units="1", icon_var_name="qv"),
)
DIAGNOSTIC_CF_ATTRIBUTES: Final[dict[str, model.FieldMetaData]] = dict(
    eastward_wind=model.FieldMetaData(standard_name="eastward_wind", units="m s-1", icon_var_name="u"),
    temperature=model.FieldMetaData(standard_name="air_temperature", units="K", icon_var_name="temperature"),
)
PRECIPITATION_CF_ATTRIBUTES: Final[dict[str, model.FieldMetaData]] = dict(
    precipitation_flux=model.FieldMetaData(standard_name="precipitation_flux", units="kg m-2 s-1"),
)


def tendency_of(base: model.FieldMetaData) -> model.FieldMetaData:
    units = "s-1" if base.units == "1" else f"{base.units} s-1"
    return model.FieldMetaData(
        standard_name=f"tendency_of_{base.standard_name}", units=units, kind=model.FieldKind.TENDENCY
    )


TENDENCY_CF_ATTRIBUTES: Final[dict[str, model.FieldMetaData]] = dict(
    temperature=tendency_of(DIAGNOSTIC_CF_ATTRIBUTES["temperature"]),
    qv=tendency_of(COMMON_TRACER_CF_ATTRIBUTES["qv"]),
)
