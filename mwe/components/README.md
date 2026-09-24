# Components MWE

Two runnable mini-models of the icon4py time loop on fake data. `model_current`
is a trimmed copy of icon4py (`main`, PR C2SM/icon4py#1436, branch
`physics_driver_tmx`): the module paths under `src/icon4py/model/` and every
class, method, attribute, argument and dict-key name are the real ones, only
grid/config/backend plumbing and stencil bodies are gone. `model_proposed` is the
`State`/`Component` design in `DESIGN.md`, with the same module and class names
so the two trees read side by side. Same `ops.py`, same `example.yaml`, same
numbers, different declarations. Eleven quantities, seven scalars, no real
stencils.

    cd mwe/components
    /path/to/icon4py/.venv/bin/python run.py
    /path/to/icon4py/.venv/bin/python -m pytest -q
    /path/to/icon4py/.venv/bin/python -m mypy model_current model_proposed run.py test_framework.py test_equivalence.py config.py ops.py

`run.py` prints the proposed model's declared dataflow for `example.yaml`, then
runs both models on four configs (the example, tmx only, no physics, no output)
and prints one row per side with `OK` and how many times each side computed
`temperature` and `u`.

Suggested reading order: `run.py` output, then `model_current/atmosphere/subgrid_scale_physics/muphys/`
next to `model_proposed/muphys.py` and `model_proposed/recipes.py`, then
`physics_driver.py` on both sides, then `driver.py` on both sides, then
`model_proposed/common/framework.py`.
