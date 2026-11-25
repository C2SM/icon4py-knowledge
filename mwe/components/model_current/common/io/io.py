import datetime

import ops


class IOMonitor:
    def __init__(self, *, variables: list[str]) -> None:
        self._field_names = variables
        self.dataset: list[tuple[datetime.datetime, str, ops.Array]] = []

    def store(self, state: dict[str, ops.Field], model_time: datetime.datetime) -> None:
        state_to_store = {field: state[field] for field in self._field_names}
        for name, field in state_to_store.items():
            self.dataset.append((model_time, name, ops.arr(field).copy()))
