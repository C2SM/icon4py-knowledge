from model_current.common.states import data, model

INPUTS_PROPERTIES: dict[str, model.FieldMetaData] = {
    "temperature": data.DIAGNOSTIC_CF_ATTRIBUTES["temperature"],
    "u": data.DIAGNOSTIC_CF_ATTRIBUTES["eastward_wind"],
}
OUTPUTS_PROPERTIES: dict[str, model.FieldMetaData] = {
    "tend_temperature": data.TENDENCY_CF_ATTRIBUTES["temperature"],
    "tend_u": data.tendency_of(data.DIAGNOSTIC_CF_ATTRIBUTES["eastward_wind"]),
}
TENDENCY_GRANULE_PORTS: dict[str, str] = {f"tend_{name}": f"ddt_{name}" for name in ("temperature", "u")}
