---
title: Declarative testing harness — prior art and research
author: havogt
tags: [testing, verification, serialbox, stencil-tests, datatests, pytest, tolerances, benchmarking]
created: 2026-06-10
status: draft
---

Background for [[personal/havogt/declarative-testing-harness/declarative-testing-harness|Declarative testing harness]].
Survey done June 2026. Facts and verbatim snippets; conclusions live in the proposal.

## 1. pace / NDSL translate tests — the closest prior art

A GT4Py port of the FV3 atmospheric model verified against Serialbox data from
Fortran. Exactly our problem. Lineage: `VulcanClimateModeling/fv3core` →
`ai2cm/pace` → `NOAA-GFDL/pace`; framework now in
[NOAA-GFDL/NDSL](https://github.com/NOAA-GFDL/NDSL) (`ndsl/stencils/testing/`),
concrete tests in [NOAA-GFDL/pyFV3](https://github.com/NOAA-GFDL/pyFV3)
(`tests/savepoint/translate/`).

### The model

One class per Fortran savepoint, `Translate{Name}`, declaring metadata dicts.
The only mandatory code is `compute_func`. A real example verbatim:

```python
class TranslateRiem_Solver_C(TranslateDycoreFortranData2Py):
    def __init__(self, grid, namelist: Namelist, stencil_factory: StencilFactory):
        super().__init__(grid, namelist, stencil_factory)
        self.compute_func = NonhydrostaticVerticalSolverCGrid(
            stencil_factory, quantity_factory=self.grid.quantity_factory,
            p_fac=self.config.p_fac,
        )
        self.in_vars["data_vars"] = {
            "cappa": {}, "hs": {}, "w3": {}, "ptc": {}, "q_con": {},
            "delpc": {}, "gz": {}, "pef": {}, "ws": {},
        }
        self.in_vars["parameters"] = ["dt2", "ptop"]
        self.out_vars = {"pef": {"kend": grid.npz}, "gz": {"kend": grid.npz}}
        self.max_error = 5e-14
```

Metadata keys per variable: `serialname`, `istart/iend/jstart/jend/kstart/kend`,
`kaxis`, `axis`, `dummy_axes`, `names_4d`, `index_variable` (Fortran 1-based
→ 0-based), `full_shape`. Empty `{}` means full domain incl. halos.

Data pipeline note: current NDSL converts Serialbox → NetCDF **once**, offline
(`ndsl-serialbox_to_netcdf`), and the harness reads only NetCDF via xarray.
Serialbox (and Boost) are needed for data generation, not test runs.

### Reporting — they use `pytest-subtests`

Every output variable is always checked; each is `with subtests.test(varname=...)`
plus `pytest.fail(str(metric), pytrace=False)`, so each failing variable is its own
subtest and the test then fails with "Only the following variables passed: …".
`pytest-subtests` is a hard dependency (NDSL PR #201). Artifacts: per-savepoint
summary logs and a NetCDF DataTree with `Fail/`/`Pass/` groups holding
`_input`/`_reference`/`_computed`/`_absolute_error` arrays.

### Tolerances — the decay story

Class defaults `max_error = 1e-14` (relative), `near_zero = 1e-18`. The single
relative metric broke down twice:

- **Near zero**: `LegacyMetric` is `|computed − reference| / reference` with
  reference zeros replaced by 1.0 — hence the `near_zero` +
  `ignore_near_zero_errors` patchwork.
- **Mixed precision**: hence `MultiModalFloatMetric` (opt-in), which passes if
  **any** of absolute (1e-13 f64 / 1e-10 f32), relative (1e-6), or ULP (≤ 1.0)
  criteria hold.

Overrides live in YAML keyed by savepoint, matched on backend and platform:

```yaml
Tracer2D1L:
  - backend: st:gt:gpu:KJI
    max_error: 1e-9
    ignore_near_zero_errors:
      tracers: 1e-9
DelnFlux:
  - max_error: 2e-13 # changes in code for mass conservation at single precision
```

Two rules worth stealing: overrides only ever **loosen**
(`if absolute_eps_override > default: ...`), and an active override is **flagged
in the report** (🔶 marker). GPU runs additionally get a blanket floor
(`max_error = max(max_error, 1e-10)`) rather than per-cause analysis.

### Where thresholds come from

The [Pace v0.2 GMD paper](https://gmd.copernicus.org/articles/16/2719/2023/):
the 1e-14 default was chosen by perturbing Fortran inputs with small
floating-point differences and observing the output spread. When a unit exceeds
it they bisect; if the difference is an intentional algorithmic change they
loosen that unit's tolerance to the measured difference.

[NDSL issue #133](https://github.com/NOAA-GFDL/NDSL/issues/133) ("Translate
tests: Automatically calculate thresholds") reports the half-finished
perturbation feature was effectively disabled (`N_THRESHOLD_SAMPLES=0`) and warns
auto-suggested thresholds "could lead to developers blindly taking over suggested
values, masking potential porting issues."

### Documented pain points

1. **Metadata duplication is their stated #1 regret** — from the pyFV3 README:
   "We currently provide a duplicate of most of the metadata in the specification
   of the unit test, but that may be removed eventually."
2. **Data-driven collection hacks.** Class lookup is
   `getattr(translate_module, f"Translate{name}")` where the module is injected
   into the framework's conftest by the consuming project — pyFV3's conftest calls
   it "This magical series of imports". Lookup originally failed silently
   (fixed late, NDSL PR #259).
3. **Test rot.** `tests/savepoint/translate/__init__.py` carries
   `# from .translate_fvsubgridz import TranslateFVSubgridZ # <-- BROKEN CODE`.
   TODOs note functions kept alive only because a translate test exists,
   i.e. savepoint granularity leaking Fortran structure into the Python code.
4. **Partial-output validation needed a global monkeypatch**
   (`enable_selective_validation()` NaN-fills non-validated regions).
5. **In-place dict mutation and max-shape buffers** are acknowledged legacy
   ("feel free to refactor"); backend-dependent shape leaks into tests.

## 2. pytest ecosystem (state mid-2026)

| tool | latest | per-field tolerance? | oracle | notes |
|---|---|---|---|---|
| `pytest-subtests` | 0.15.0 | n/a | n/a | pytest-dev; **merged into pytest 9 core**, plugin then archived |
| `pytest-regressions` | 2.11.0 | **yes** | auto `.npz` | `tolerances={'U': Tolerance(atol=1e-2)}`, `default_tolerance`, `--force-regen` |
| `pytest-arraydiff` | 0.7.0 | per-test | golden file | astropy; `@pytest.mark.array_compare(rtol=…)` |
| `pytest-regtest` | 2.5.1 | per-call | golden file | `snapshot.check(arr, atol=…, rtol=…)` |
| `pytest-mpl` | 0.19.0 | single RMS | baseline image | the `--mpl-generate-path` baseline pattern |
| `syrupy` / `pytest-snapshot` | 5.3.2 / 0.9.0 | **no** | snapshot | exact-match by architecture |
| `parametrize_from_file` | 0.21.0 | n/a | n/a | params in YAML/TOML next to the test module |
| `pytest-cases` | 3.10.1 | n/a | n/a | cases-as-functions, not cases-as-data |
| `tavern` | 3.6.0 | n/a | n/a | reference impl of full test-as-data collection |

Key facts:

- **`pytest-subtests`**: `with subtests.test(msg=…, **kwargs):` — each failing
  context reported separately while the test continues. In pytest 9 core the
  status is `SUBFAILED`, and the
  [docs](https://docs.pytest.org/en/stable/how-to/subtests.html) still label it
  *experimental*: "behavior, particularly how failures are reported, may evolve";
  subtests "cannot be referenced individually from the command line". xdist
  friction: subtest reports are serialized over execnet, so non-plain payloads
  break (a `StrEnum` msg raises `execnet.gateway_base.DumpError`,
  [pytest-xdist #1161](https://github.com/pytest-dev/pytest-xdist/issues/1161));
  distribution granularity stays per-test.
- **`pytest-regressions`** is the only plugin with genuine per-key tolerances:
  `tolerance_args = self._tolerances_dict.get(k, self._default_tolerance)`, then
  `np.isclose(..., equal_nan=True, **tolerance_args)`. Reference `.npz` files are
  named after module/function by a pytest-datadir convention; `--force-regen`
  rewrites them.
- **Snapshot tools cannot do tolerance.** Comparison happens on serialized data,
  so `pytest.approx` cannot participate — confirmed in
  [syrupy #438](https://github.com/tophat/syrupy/issues/438) and
  [#889](https://github.com/syrupy-project/syrupy/issues/889). Sanctioned
  workaround is `matchers` that *quantize* values before serialization.
- **`tavern`** implements `pytest_collect_file` returning a custom `YamlFile`
  collector, matching a configurable filename regex. Reported costs: debugging is
  via logging config not a debugger; failure output is verbose with unclear
  attribution ([issue #186](https://github.com/taverntesting/tavern/issues/186));
  no IDE navigation into YAML; third-party integrations need special-casing.
- **`pytest-check`** (2.8.0) is the alternative collect-all mechanism: `with check:`
  contexts aggregate into one failing test, rather than separately-counted outcomes.

## 3. ESM verification tooling

### probtest (MeteoSwiss, used by ICON)

[github.com/MeteoSwiss/probtest](https://github.com/MeteoSwiss/probtest). Derives
per-(variable, timestep, statistic) tolerances from a CPU ensemble in which
selected input fields (T, QV) are perturbed in the least significant digits. A
test build passes if its deviation from the unperturbed reference is within
`factor ×` the ensemble spread (default `--factor 5`). "Variables are not
excluded, but rather a tolerance is computed for each variable."

Error metric (`util/dataframe_ops.py`), verbatim:

```python
def compute_rel_diff_dataframe(df1, df2):
    """This implementation is similar to the numpy.isclose function:
    (absolute(a - b) <= (atol + rtol * absolute(b)) ),
    assuming atol==rtol and moving the right hand side to the left."""
    out = (df1 - df2) / (1.0 + df1.abs())
    return out.abs()
```

Stats are CSV with row MultiIndex `(file_ID, variable, height)` and column
MultiIndex `(time, statistic)` over `mean/max/min`; tolerance CSV collapses
height. Declaration granularity is **file patterns**
(`--file-id NetCDF "*atm_3d_ml*.nc"`), never individual variables.

ICON's own side: `checksuite.icon-dev` modes `b/u/r/n/m/o/t/p/c/g` (t = the
probtest tolerance check; u/r/n/m/o are bit-identity checks). Experiments and
their tolerance settings are declared in YAML under `scripts/experiments/`, e.g.

```yaml
- name: mch_kenda-ch1_small
  tolerance:
    perturb_amplitude:
      - mixed: 1e-2
      - double: 1e-14
    file_id:
      - NetCDF: ['*atm_3d_ml*.nc', '*iaf*', '*lfff0*']
```

### COSMO technical testsuite

[C2SM-RCM/testsuite](https://github.com/C2SM-RCM/testsuite). Tests declared in
`testlist.xml` with pluggable `<checker>` scripts. `tolerance_check.py` compares
COSMO's `YUPRTEST` per-variable/per-level/per-step output against a `TOLERANCE`
file next to the namelists — per-variable, per-step thresholds with a `*`
wildcard row:

```
   minval = 1e-12
    steps =          0          1          2 ...        100
        * =   0.00e+00   2.00e-13   2.00e-13 ...   4.00e-11
      eta =   0.00e+00   7.00e-15   7.00e-15 ...   2.00e-13
```

### gridtools_verification (C++, the original inspiration)

[GridTools/gridtools_verification](https://github.com/GridTools/gridtools_verification).
`field_collection<T>`: `register_input_field(name, field)`,
`register_output_and_reference_field(...)`, `load_iteration(int)`,
`verify(error_metric)`, `report_failures()`.
`error_metric<T>(rtol, atol)` with `equal(a,b) := |a-b| <= atol + rtol*|b|`.
`boundary_extent(iMinus, iPlus, jMinus, jPlus, kMinus, kPlus)` excludes halo
points. Plus `verification_result`, `verification_reporter`.

### CIME / cprnc (E3SM, CESM)

Test names *are* the declaration: `TESTTYPE[_MODIFIERS].GRID.COMPSET[.MACHINE_COMPILER]`,
e.g. `SMS.f19_f19.A.melvin_gnu`; types like `ERS` (exact restart), `REP`
(reproducibility), `PEM`/`PET` (task/thread counts) are reusable comparison
recipes. Baselines via `create_test -g -b master` / `-c -b master`; `bless_test_results`
updates them. `cprnc` reports per-field RMS, normalized RMS, "avg decimal digits",
verdict `IDENTICAL`/`DIFFERENT` — **no per-field tolerances**; history comparisons
are bit-for-bit. Statistical acceptance is a separate tool
([pyCECT](https://github.com/NCAR/PyCECT): PCA over an accepted ensemble).

### Other serialbox / single-column harnesses

- **ECMWF CLOUDSC dwarf** validates against HDF5 or Serialbox reference data;
  verification is a hard-coded per-field Fortran `VALIDATE` interface (L1-norm
  style errors), no declarative tolerance files.
- **ai2cm/physics_standalone** hard-codes `IN_VARS`/`OUT_VARS` lists per scheme
  and compares with `np.isclose(..., equal_nan=True)` at default tolerances.
- **CCPP** declares scheme *interfaces* via per-variable `.meta` metadata tables
  (`standard_name`, `units`, `dimensions`, `intent`), matched host↔scheme by
  `standard_name` — interface metadata, not verification tolerances.

## 4. Inventory of icon4py's current suite

Measured on `main` (June 2026):

- **240** `@pytest.mark.datatest` markers across **45** files; none decorate a
  class, so ≈240 datatest functions.
- **200** `StencilTest` subclasses.
- Exactly **2** shared verification helpers: `verify_diffusion_fields`
  (`model/atmosphere/diffusion/tests/diffusion/utils.py:16`) and
  `verify_advection_fields` (`model/atmosphere/advection/tests/advection/utils.py:128`).
  `dallclose` is used directly in **37** test files.
- All verification is fail-on-first (`assert test_utils.dallclose(...)`).
- `StencilTest._verify_stencil_test` hardcodes `rtol = 3e-6` for every subclass,
  with a TODO recording that it was raised from `1e-7` to cover CI discrepancies
  "probably [from] derivatives of random data".
- Config-conditional verification exists in exactly one place: `verify_diffusion_fields`
  checks `div_ic`/`hdef_ic`/`dwdx`/`dwdy` only when
  `config.shear_type >= TurbulenceShearForcingType.VERTICAL_HORIZONTAL_OF_HORIZONTAL_WIND`.
  Its tolerances: `div_ic` atol=1e-16, `hdef_ic` atol=1e-13, `dwdx`/`dwdy` atol=1e-18,
  `vn` atol=1e-8 rtol=1e-9, `w` atol=1e-14, `theta_v`/`exner` at `dallclose` defaults.
- Savepoint→state construction is repeated inline across test bodies and in
  per-package `utils.py` (`construct_interpolation_state`, `construct_diagnostic_init_state`,
  `construct_metric_state`, `construct_prep_adv`, …), alongside the `construct_*`
  methods already on `serialbox.py` savepoint classes.
- Benchmarking (`pytest-benchmark` + GT4Py metrics) exists only in `StencilTest`.
