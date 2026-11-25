import dataclasses

from icon4py.model.common import field_type_aliases as fa, type_alias as ta


@dataclasses.dataclass
class PrepAdvection:
    mass_flx_me: fa.EdgeKField[ta.wpfloat]
