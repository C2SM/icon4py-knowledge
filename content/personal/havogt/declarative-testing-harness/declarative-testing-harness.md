---
title: Declarative testing harness
author: havogt
tags: [testing, verification, serialbox, stencil-tests, datatests, pytest, tolerances, benchmarking]
created: 2026-06-10
status: draft
---

> **TL;DR** Stencil tests and serialbox data tests are the same test shape with
> different input and oracle sources; give them one declarative core — fields
> declared by name with per-field tolerances, verified as pytest subtests — plus
> two thin presets, and stop hand-writing the savepoint→state boilerplate.

## Problem / motivation

icon4py has two large, structurally similar test families:

| | count | inputs | oracle |
|---|---|---|---|
| `StencilTest` subclasses | 200 | generated (random) | computed (numpy `reference()`) |
| `@pytest.mark.datatest` functions | 240 (45 files) | recorded (init savepoint) | recorded (exit savepoint) |

They differ only in **where the inputs come from** and **where the reference
comes from**. Everything after that — compare each output field against a
reference under a tolerance, report what drifted, optionally benchmark the
subject — is identical. Today they share none of it.

Concrete pain:

1. **Verification is fail-on-first.** There are exactly two shared helpers
   (`verify_diffusion_fields`, `verify_advection_fields`); everything else is
   inline `assert test_utils.dallclose(...)` across 37 test files. The first
   field that drifts raises and you never learn whether the other seven also
   drifted. That is precisely the wrong behaviour when chasing a multi-field
   regression (e.g. rank-count reproducibility work).
2. **Tolerances are ad-hoc and invisible.** They live as positional kwargs
   inside assertion lines, with no policy and no provenance. `StencilTest`
   hardcodes a single `rtol=3e-6` for all 200 subclasses, with a TODO
   explaining it was raised from `1e-7` to paper over CI discrepancies.
3. **Savepoint→state mapping is copy-pasted.** A large share of every datatest
   body is mechanically rebuilding state dataclasses out of same-named savepoint
   accessors (`DiffusionDiagnosticState(hdef_ic=sp.hdef_ic(), div_ic=sp.div_ic(), ...)`).
4. **Benchmarking is arbitrarily coupled to stencil tests.** `StencilTest` gets
   `pytest-benchmark` and GT4Py metrics; datatests get nothing. There is no
   reason a granule-level datatest should not be benchmarked — it was just
   easier to add it on one side.

## Proposal

Three layers, each independently useful and independently adoptable.

### Layer 1 — `verification.py`: checks as data, subtests as reporter

```python
@dataclasses.dataclass(frozen=True)
class Tolerance:
    atol: float = 0.0
    rtol: float = 1.0e-12
    equal_nan: bool = False

@dataclasses.dataclass(frozen=True)
class Check:
    name: str
    ref: str | None = None          # reference key, if it differs from `name`
    atol: float | None = None       # None -> policy default
    rtol: float | None = None
    equal_nan: bool | None = None
    refslice: tuple[slice, ...] = (slice(None),)
    gtslice: tuple[slice, ...] = (slice(None),)

DATA_DEFAULT = Tolerance(rtol=1e-12)                     # == test_utils.dallclose
STENCIL_DEFAULT = Tolerance(rtol=3e-6, equal_nan=True)   # == today's StencilTest

def compare_field(actual, desired, *, atol, rtol, equal_nan) -> FieldResult: ...
def check_fields(subtests, actual, expected, checks, *, defaults) -> None: ...
```

`check_fields` runs each `Check` inside `with subtests.test(field=...)`, so
**every** field is compared and each mismatch is reported independently. The
tolerance formula stays `numpy.isclose` (`|a-b| <= atol + rtol*|b|`), so nothing
about existing pass/fail semantics changes.

What a multi-field failure looks like:

```
tmp/test_demo_subtests.py uuF                                            [100%]

=================================== FAILURES ===================================
_________________ test_run_diffusion_single_step (field='vn') __________________
'vn': 1/3 entries (33.33%) exceed atol=0, rtol=1e-12; max abs diff 5.000e-03 at index (0, 2) (computed 3.000000e+00, reference 3.005000e+00).
_______________ test_run_diffusion_single_step (field='theta_v') _______________
'theta_v': 1/3 entries (33.33%) exceed atol=0, rtol=1e-12; max abs diff 5.000e-02 at index (0, 2) (computed 3.020000e+02, reference 3.020500e+02).
________________________ test_run_diffusion_single_step ________________________
contains 2 failed subtests
=========================== short test summary info ============================
SUBFAILED(field='vn') tmp/test_demo_subtests.py::test_run_diffusion_single_step
SUBFAILED(field='theta_v') tmp/test_demo_subtests.py::test_run_diffusion_single_step
FAILED tmp/test_demo_subtests.py::test_run_diffusion_single_step - contains 2...
```

`uu` are passing subtests. Failing fields are individually addressable in the
summary. No custom report formatter to maintain — this is pytest's own subtests
machinery (merged into pytest 9 core; `pytest-subtests` bridges until then).

**This layer is implemented and green** — see the prototype branch
[`havogt/icon4py@declarative-verification`](https://github.com/havogt/icon4py/tree/declarative-verification)
(module + 19 unit tests, pre-commit clean).

### Layer 2 — `states.py`: the savepoint↔state mapping, declared once

```python
def from_savepoint(state_cls, sp, **overrides):
    return state_cls(**{
        f.name: overrides[f.name] if f.name in overrides else getattr(sp, f.name)()
        for f in dataclasses.fields(state_cls)
    })
```

State-dataclass field names already match savepoint accessor names almost
everywhere. The rare renames become explicit `overrides` at the one place they
occur. This deletes the copy-pasted `construct_*` blocks in the per-package test
utils. Where a mapping is stable it can later migrate onto the state class
itself — which is where it arguably belongs (see the pace/NDSL regret in the
research appendix).

### Layer 3 — `harness.py`: one core, two presets

```python
class VerificationTest:
    OUTPUTS: ClassVar[tuple[str | Check, ...]]   # or a staticmethod taking fixtures
    TOLERANCE: ClassVar[Tolerance]

    def expected(self, checks, **deps) -> Mapping[str, Any]: ...
    def subject(self, **deps) -> Mapping | tuple[Mapping, Callable]: ...
```

The synthesized test body pins the order:

```
resolve OUTPUTS -> expected(...) -> subject(...) -> check_fields(...) -> benchmark(timed)
```

Both orderings are load-bearing, not stylistic:

- **Oracle before subject.** GT4Py programs write in place into `input_data`, and
  `asnumpy()` on CPU is a view. The reference must be snapshotted before the
  subject runs. (Today's `StencilTest` already does this; a naive unification
  silently breaks it.)
- **Verify before benchmark.** The `timed` callable mutates the very fields under
  verification — a stencil re-runs on the same buffers, and `diffusion.run()`
  advances the prognostic state.

Benchmarking is orthogonal and opt-in by *return shape*: `subject` returning
`(outputs, timed)` gets benchmarked, returning `outputs` does not. No `BENCHMARK`
flag needed, and datatests can finally be benchmarked.

`StencilTest` becomes a preset whose author-facing API is **unchanged** for all
200 subclasses (`PROGRAM`, `STATIC_PARAMS`, the `input_data` fixture,
`reference()`); only its internal `_verify_stencil_test` is replaced by
`check_fields`. `DataTest` is the other preset:

```python
class TestRunDiffusionSingleStep(harness.DataTest):
    EXIT = "savepoint_diffusion_exit"

    @staticmethod
    def OUTPUTS(*, experiment):                       # dynamic: config-conditional
        base = (Check("vn", atol=1e-8, rtol=1e-9), Check("w", atol=1e-14),
                "theta_v", "exner")
        if experiment.config.shear_type >= TurbulenceShearForcingType.VERTICAL_HORIZONTAL_OF_HORIZONTAL_WIND:
            return (*base, Check("div_ic", atol=1e-16), Check("hdef_ic", atol=1e-13),
                    Check("dwdx", atol=1e-18), Check("dwdy", atol=1e-18))
        return base

    @staticmethod
    def run(*, savepoint_diffusion_init, diffusion_granule):
        sp = savepoint_diffusion_init                 # an ordinary fixture dep
        diagnostic = states.from_savepoint(DiffusionDiagnosticState, sp)
        prognostic = states.from_savepoint(PrognosticState, sp)
        timed = lambda: diffusion_granule.run(diagnostic_state=diagnostic,
                                              prognostic_state=prognostic,
                                              dtime=sp.get_metadata("dtime")["dtime"])
        timed()
        return {**vars(prognostic), **vars(diagnostic)}, timed
```

Notes on the shape, each earned by discarding an earlier draft:

- There is **no `INIT`/`INPUTS`/`make_inputs`.** An earlier version had the
  harness preload named accessor fields from a declared init savepoint. It does
  not pay for itself: real datatests need the savepoint anyway (for
  `construct_prognostics()`, `get_metadata("dtime")`, tracer extraction), so the
  savepoint ended up named twice — once as a string, once as a fixture. The init
  savepoint is just a fixture dependency of `run`, named once. Only `EXIT` is a
  harness concept, because only the oracle needs it.
- A `make_inputs` seam returning "a field dict for stencils, a savepoint for
  datatests" is fake symmetry: one name, two types, no shared behaviour. Inputs
  are not a harness concern.
- `OUTPUTS` must be allowed to be a fixture-consuming callable, because
  verification is genuinely config-conditional in at least one real case (the
  diffusion `shear_type` diagnostics above).
- The granule/config/geometry construction moves into a `diffusion_granule`
  fixture — per-component glue shared by several tests, which is exactly what
  fixtures are for. Parametrization stays plain `@pytest.mark.parametrize`.

### Migration path

Each step ships on its own:

1. `verification.py` + unit tests. Then swap the two `verify_*_fields` helpers
   and the inline `dallclose` sites onto `check_fields` — every datatest gains
   per-field reporting. (Callers must request the `subtests` fixture, so this is
   a one-line signature change per test, not zero.)
2. `states.from_savepoint`; delete the copy-pasted `construct_*` blocks.
3. `harness.DataTest`; migrate diffusion as PoC, keeping the existing test as
   oracle until validated.
4. Swap `StencilTest`'s verification onto `check_fields`; author API untouched.

## Alternatives considered

- **Fully declarative, test-as-data collection** (YAML manifests collected via
  `pytest_collect_file`, as tavern does; or pace/NDSL's "glob the savepoints,
  look up `Translate{Name}` by naming convention"). Rejected: both projects
  document the costs — no debugger, no IDE navigation into the spec, confusing
  failure attribution, conftest module-injection hacks, and silent rot (NDSL ships
  a `# <-- BROKEN CODE` line in their test registry). Additionally icon4py's
  savepoints are *metadata-selected* (date/istep/substep/linit), not
  name-enumerable, so the collection story does not even map cleanly. Keeping a
  short, breakpoint-able `run()` in Python is the right floor.
- **`pytest-regressions`** (`ndarrays_regression`, per-key tolerances,
  `--force-regen`). It is the only plugin with real per-field tolerances, but it
  solves oracle *storage* — auto-generated `.npz` baselines. We already have an
  oracle (serialbox). Worth revisiting only for tests that have no recorded
  reference.
- **Snapshot tools** (`syrupy`, `pytest-snapshot`). Rejected on architecture:
  they compare *serialized* output, so numeric tolerance is impossible. Also, a
  snapshot is a change-detector, not a correctness oracle; we have an independent
  oracle and should keep it.
- **Hand-rolled collect-all reporter.** The first prototype did this (a formatted
  per-field OK/FAIL table, one `pytest.fail` at the end). `pytest-subtests` does
  it natively, integrates with the summary and with `-k`/reporting plugins, and
  is now core pytest. Deleting the custom reporter is a strict win.
- **Keeping two separate harnesses** and only fixing datatests. This is what the
  first iteration of this idea did. It leaves `StencilTest`'s fail-on-first
  verification and its hardcoded global tolerance untouched, and permanently
  denies datatests benchmarking.
- **Ensemble-derived tolerances** (probtest-style: perturb inputs, take the
  spread as the tolerance). The principled answer to "where do tolerances come
  from", and ICON already does this at the system-test level. Out of scope here,
  and NDSL's experience is a caution — see open questions.

## Open questions / conflicts

- **`pytest-subtests` as a dependency.** It changes failure presentation
  suite-wide (`SUBFAILED` lines, per-field counts). It is pytest-dev maintained
  and merged into pytest 9 core, and pace/NDSL independently landed on it. Caveat:
  under `xdist` the subtest label must be a plain serializable string, and
  distribution granularity stays per-test. Is the presentation change acceptable
  for CI consumers?
- **Where does the savepoint↔state mapping belong?** Layer 2 puts it in
  `model/testing`. NDSL's stated top regret is that their translate-test metadata
  duplicates the model's own variable metadata. Should `from_savepoint` be a
  test-side reflection helper (proposed), or should state classes carry their
  serialnames? The latter is more correct and more invasive.
- **Tolerance overrides as data.** Every comparable project (NDSL YAML keyed by
  savepoint × backend × platform; COSMO's per-variable/per-step `TOLERANCE`
  tables; probtest CSV) ends up with tolerances in a file, not in code. Not
  proposed now, but `Check` resolution should keep a lookup seam. If adopted,
  steal NDSL's two safety rules: overrides may only **loosen**, and active
  overrides are **flagged in the report**. Their unresolved issue #133 warns that
  auto-derived thresholds get blindly accepted and mask porting bugs.
- **`StencilTest` preset details.** Its GT4Py metrics extraction counts exact
  program invocations (`warmup*iters + (2 if skip_verification else 3)`); any
  change to how often the subject runs silently breaks that arithmetic. And
  `--skip-stenciltest-verification` today runs the program *zero* times before
  benchmarking, which the unified flow would change. Both must be re-derived
  inside the preset.
- **Tuple-valued outputs.** `_verify_stencil_test` supports an output being a
  tuple of fields; `check_fields` must grow element-wise support before the
  `StencilTest` swap.
- **Overlap with other proposals:** none known — this is currently the first
  proposal in this knowledge base. If someone is reworking fixtures, backends, or
  `serialbox.py` accessors, this touches all three; please link here.

## Appendices

- [[personal/havogt/declarative-testing-harness/declarative-testing-harness_research|Prior art and research]] —
  pace/NDSL translate tests, the pytest plugin ecosystem, ESM verification tooling
  (probtest, COSMO testsuite, CIME/cprnc, gridtools_verification), and an
  inventory of icon4py's current suite.
- Prototype (Layer 1 only):
  [`havogt/icon4py@declarative-verification`](https://github.com/havogt/icon4py/tree/declarative-verification).
