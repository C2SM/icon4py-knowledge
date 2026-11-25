import datetime
from typing import Protocol, TypeVar

from model_current.common.states import model

Ins = TypeVar("Ins", bound=str)
Outs = TypeVar("Outs", bound=str)


class Component(Protocol[Ins, Outs]):
    @property
    def inputs_properties(self) -> dict[Ins, model.FieldMetaData]: ...

    @property
    def outputs_properties(self) -> dict[Outs, model.FieldMetaData]: ...

    def __call__(
        self, state: dict[Ins, model.DataField], time_step: datetime.datetime
    ) -> dict[Outs, model.DataField]: ...
