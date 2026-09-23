import dataclasses
import pathlib

import yaml


@dataclasses.dataclass(frozen=True)
class Config:
    output_variables: tuple[str, ...]
    physics: dict[str, int]


def load(path: pathlib.Path) -> Config:
    raw = yaml.safe_load(path.read_text())
    return Config(output_variables=tuple(raw["output_variables"]), physics=dict(raw["physics"]))
