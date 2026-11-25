import dataclasses

from icon4py.model.common import dimension as dims

from model_current.common.states import data, model

INPUTS_PROPERTIES: dict[str, model.FieldMetaData] = {
    "te": data.DIAGNOSTIC_CF_ATTRIBUTES["temperature"],
    "qv": data.COMMON_TRACER_CF_ATTRIBUTES["qv"],
}
OUTPUTS_PROPERTIES: dict[str, model.FieldMetaData] = {
    "tend_temperature": data.TENDENCY_CF_ATTRIBUTES["temperature"],
    "tend_qv": data.TENDENCY_CF_ATTRIBUTES["qv"],
    "pflx": dataclasses.replace(data.PRECIPITATION_CF_ATTRIBUTES["precipitation_flux"], dims=(dims.CellDim,)),
}
