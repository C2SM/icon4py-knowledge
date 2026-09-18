from datetime import datetime

import ops


class OutputWriter:
    def __init__(self) -> None:
        self.records: list[tuple[datetime, ops.Array]] = []

    def write(self, simulation_time: datetime, fields: dict[str, ops.Field]) -> None:
        for f in fields.values():
            self.records.append((simulation_time, ops.arr(f).copy()))
