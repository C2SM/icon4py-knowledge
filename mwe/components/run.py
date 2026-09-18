from typing import Any

import numpy as np

from model_current import driver as current
from model_proposed import driver as proposed
from model_proposed.common.framework import dataflow
import ops


def run_both() -> tuple[dict[str, Any], dict[str, Any]]:
    a, b = current.TimeLoop(), proposed.TimeLoop()
    a.run(ops.N_STEPS)
    b.run(ops.N_STEPS)
    return a.results(), b.results()


def compare(results: tuple[dict[str, Any], dict[str, Any]]) -> list[str]:
    a, b = results
    bad = [name for name in a if name != "records" and not np.array_equal(a[name], b[name])]
    bad += [
        f"records[{i}]"
        for i, (x, y) in enumerate(zip(a["records"], b["records"], strict=True))
        if x[0] != y[0] or not np.array_equal(x[1], y[1])
    ]
    return bad


if __name__ == "__main__":
    loop = proposed.TimeLoop()
    p = loop.physics
    print(dataflow(loop.dycore, loop.diffusion, loop.advection, p.derived, p.muphys, p.tmx, p.eos, p.projection, loop.writer))
    mismatches = compare(run_both())
    print("OK" if not mismatches else f"MISMATCH: {mismatches}")
    raise SystemExit(1 if mismatches else 0)
