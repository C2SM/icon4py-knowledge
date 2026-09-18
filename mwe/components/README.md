# Components MWE

Two runnable mini-models of the icon4py time loop on fake data: `model_current`
(today's shape: dict-based physics state, `TimeStepPair`, granule signatures)
and `model_proposed` (the `State`/`Component` design in `DESIGN.md`). Same
`ops.py`, same numbers, different declarations. Ten quantities, eight scalars,
no real stencils.

    cd mwe/components
    /path/to/icon4py/.venv/bin/python run.py
    /path/to/icon4py/.venv/bin/python -m pytest -q
    /path/to/icon4py/.venv/bin/python -m mypy model_proposed run.py

`run.py` prints the proposed model's declared dataflow and `OK` when both
models agree on every quantity and every output record after four steps.
