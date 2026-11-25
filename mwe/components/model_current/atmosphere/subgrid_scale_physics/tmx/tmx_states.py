import dataclasses

from icon4py.model.common import field_type_aliases as fa, type_alias as ta


@dataclasses.dataclass
class TmxTendencyState:
    ddt_temperature: fa.CellKField[ta.wpfloat]
    ddt_u: fa.CellKField[ta.wpfloat]
