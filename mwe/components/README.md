# Components MWE

Two runnable mini-models of the icon4py time loop on fake data. `model_current`
is a trimmed copy of icon4py (`main`, PR C2SM/icon4py#1436, branch
`physics_driver_tmx`): the module paths under `src/icon4py/model/` and every
class, method, attribute, argument and dict-key name are the real ones, only
grid/config/backend plumbing and stencil bodies are gone. `model_proposed` is
the same model written against the `State`/`Component` design, with module and
class names chosen so the two trees can be read side by side. Same `ops.py`, same
`example.yaml`, same numbers, different declarations.

The design is built as a stack of branches, one layer per PR, each a readable
diff on the previous one. `DESIGN.md` has one section per layer: the problem it
solves, what it adds, what it costs. The tip of the stack is the full design.

    cd mwe/components
    /path/to/icon4py/.venv/bin/python run.py
    /path/to/icon4py/.venv/bin/python -m pytest -q
    /path/to/icon4py/.venv/bin/python -m mypy model_current model_proposed run.py test_framework.py test_equivalence.py config.py ops.py

`run.py` runs both models on five configs (the example, tmx only, no physics,
no output, two prognostics out) and prints one row per side with `OK` and how many times each side
computed `temperature`, `u` and `theta_v` on half levels. All comparisons are
bit-exact.

Suggested reading order: `run.py` output, then
`model_current/atmosphere/subgrid_scale_physics/muphys/` next to
`model_proposed/muphys.py`, then `physics_driver.py` on both sides, then
`driver.py` on both sides, then `model_proposed/common/framework.py`.
