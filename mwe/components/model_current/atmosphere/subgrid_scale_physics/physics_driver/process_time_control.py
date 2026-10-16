import dataclasses
import datetime


@dataclasses.dataclass(frozen=True)
class ProcessTimeControl:
    interval: datetime.timedelta
    start_date: datetime.datetime

    def is_active(self, simulation_current_datetime: datetime.datetime) -> bool:
        elapsed = simulation_current_datetime - self.start_date
        return elapsed % self.interval == datetime.timedelta(0)
