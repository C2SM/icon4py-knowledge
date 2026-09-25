import dataclasses
import enum
from collections.abc import Sequence
from typing import Any

import gt4py.next as gtx

type DataField = gtx.Field[Any, Any]


class FieldKind(enum.StrEnum):
    TENDENCY = "tendency"


@dataclasses.dataclass(frozen=True, kw_only=True)
class FieldMetaData:
    standard_name: str
    units: str
    icon_var_name: str | None = None
    dims: Sequence[gtx.Dimension] | None = None
    kind: FieldKind | None = None
