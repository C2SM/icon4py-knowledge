---
title: Model state — what ICON-sc settles
author: jcanton
tags: [state, model-state, icon-sc, components, contracts, bind-time, prior-art, upstream-bugs]
created: 2026-07-30
status: draft
---

> Appendix to [[personal/jcanton/model-state/model-state|Model state — requirements and design options]].
> [ICON-sc](https://github.com/) is egparedes' from-scratch prototype of a better
> component/state design: a sympl+Tasmania composition layer over a zero-copy device-field
> boundary, **hosting** icon4py granules rather than forking them. It is the closest thing to
> an independent test of this document's thesis. Paths below are relative to the ICON-sc root.

## Calibration — read this before quoting anything

| | |
|---|---|
| Effort | **six days**, agent-driven (work units S01–S14, 2026-07-08→13), one implementer + one reviewer |
| Published | **nothing pushed to any remote**; 7 human sign-offs still `pending`; zero external users |
| GPU | **zero execution, ever.** `test-gpu.yml` runs on `ubuntu-latest` and asserts GPU tests *skip* |
| MPI | **zero.** `single_node_exchange` hard-defaulted at every construction site; `test-mpi.yml`'s `mpirun -n 4` is a shell comment |
| Physics | 2 of ~11 NWP schemes (satad, graupel). No radiation, convection, turbulence, land |
| Data | no GRIB2, no ExtPar, no analysis. `iau_init=True` raises `NotImplementedError` |
| Tiers | T0 and T1 built; **T2 (CUDA graph) and T3 (native driver) are 5-line roadmap stubs** |

The internal review discipline is genuinely strong — it caught a latently-red CI test and a
tolerance loosening across six fields with fabricated provenance. That is not the same thing as
production contact. `docs/architecture/icon-sc_architecture.md` is a **design proposal (v1.3)**;
much of what it describes most confidently is unbuilt.

## It confirms the thesis

`plan/bind.py` is **1732 lines**; `state/vault.py` is **203**. The compiler is 8.5× the
container. `test_plan_zero_traffic.py:104` proves **zero name lookups per step** with an
instrumented counting dict, and forbids frames from `facade`, `components/base`, `contracts`,
`xarray` and `pint` inside `run_step`.

The thesis is stated independently at `arch:338`, worth lifting verbatim:

> nothing about the interfaces changes during execution … so every lookup performed in the loop
> is recomputing an invariant; (b) once (a) is exploited, the residual cost is pure dispatch …
> which is a runtime problem, not a compiler problem.

No component can reach the container: `array_call` receives two dicts the compiler built once at
materialize time (`bind.py:1626`). Buffer **adoption** is the primary path — `from_state` never
allocates, adopts `.data`, *"never `.values`: no duck-array coercion"* (`vault.py:113`).

## …and refutes three things in the main document

**1. "If any object it created is still reachable when the first stencil runs, it has failed"
is too strong.** ICON-sc's working system violates it: the vault is live at run time
(`plan.run_step(vault, i)`, `bind.py:1686`; `Swap` ops hold the vault, `ops.py:69`; the guard
reads `vault.epoch` **every step**, `bind.py:1713`). Two things force it, both load-bearing:
something must hold the buffers so a swap can retarget the public view, and something must carry
the counters so a stale wiring raises instead of binding dead buffers.

Amended test: *nothing a **component** can reach survives; what survives is index-addressed
only, holds no names on the step path, and is an instance rather than a module-level global*
(`context.py:198` — created per `ctx.timeloop` call; there is no `get_state()`).

**2. The performance argument was wrong.** `arch:371`: *"a dict lookup is ~40–60 ns and slotted
attribute access ~20–40 ns, **but those were never the real cost**."* And the measured payoff of
the entire negotiation/execution split on a real model is **6.7 %** (JW R02B04×35, gtfn_cpu,
3.68 → 3.43 s/step, `0014/report.md:141`), against 64–101× on a kernel-free toy.

**Justify typed dataclasses on gt4py's structural prohibition (R5), Fortran buffer adoption
(R4), type-checkability and explicit ownership — never on speed.**

**3. egparedes rejects the static-dataclass premise, with our exact use case in view**
(`arch:371`):

> The schema is configuration-dependent (the tracer set alone varies), so **no static dataclass
> can be the public state type.**

This is answerable in our framing precisely because ours is a setup-time *emitter*, not a static
type — but **only if M11 (conditional allocation from config predicates) is real**. M11 is
**entirely absent from ICON-sc**; no predicate anywhere decides slot existence. Leaving M11 as a
one-line row in the mechanism table does not defuse this objection.

**Also: R4 is not solved there.** ICON-sc *is* the driver and owns allocation (`arch:286`). Any
published output not already in the vault gets `ctx.allocator.empty()`d (`bind.py:1573`) — the
one thing R4 forbids. `EgressPlan` (caller-provided buffers) exists and is explicitly *"not
exercised by the compiler"*. Its two hosted granules copy in and out every step —
**17 full-field memcpys per Δt, ~100 MB on R02B04×35** (`dycore.py:945`, `diffusion.py:472`) —
which is exactly the traffic the embedded path cannot pay.

## Adopt now

| # | Idea | Where | Solves | Size |
|---|---|---|---|---|
| A1 | **Units as identity-validation, never conversion.** One canonical unit per name, checked at class creation; Pint lazily imported and quarantined by a subprocess test proving it never enters `sys.modules` on the apply path. `("degC","K")`, `("hPa","Pa")`, `("g/kg","1")` all raise; `("m s-1","m/s")` is free | `state/units.py:66-108`; `contracts/checkers.py:211` | E9. Strictly stronger than our M8 text | ~110 LOC, no deps |
| A2 | **`icon:` namespace, two-way invariant**: unprefixed ⇒ claims CF identity; no CF name ⇒ **must** be `icon:<name>`; both directions enforced at registration. Measured split **18 CF / 72 `icon:`** | `state/names.py:11-17, 85-114` | E9, and the live `metrics_attributes.py:106` collision, by construction. Answers open question 9 empirically — 80% of an atmospheric model has no CF name | S |
| A3 | **`origin` / K-domain anchor as first-class metadata, validated in wiring.** gt4py fields carry a *domain*, not a shape | `icon/components/dycore.py:551`; dossier `0013/report.md:186-223` | **M2 extension + M3 check.** Same wound as E8 (`factory.py:544` erases `KHalfDim→KDim`) | S |
| A4 | **Coverage test: hand-map keys ≡ `dataclasses.fields(Target)`** | `0012/report.md §1` | E6, E7 — makes drift a red test *today*, zero design commitment | ~10 LOC/site |
| A5 | **Per-call shape check on caller-provided output buffers** — dim-name equality does not imply shape equality | `components/base.py:283` | **E2 directly.** `fa.CellKField[float]` cannot express `nlev` vs `nlev+1` | XS |
| A6 | **Validate declared I/O at class creation (`__init_subclass__`)**, plus cross-dict dims/units consistency and alias bijectivity; `ContractViolation(field, component, kind, actual, target)` batched into one error | `components/base.py:122`; `checkers.py:143-224` | M3, which is currently **completely inert** in icon4py | ~40 LOC |
| A7 | **Three separate invalidation domains** — `epoch` (identity change ⇒ wiring stale, raises), `generation` (view change ⇒ only cached views stale), `schema_hash` — plus `renegotiate_and_diff` in debug builds, re-running the wiring every N steps and diffing line by line | `state/vault.py:10-19`; `plan/guards.py:63-92` | **Answers open question 8: do not freeze.** Mutation stays legal; running against a stale wiring raises. Better than a hard freeze, which forbids late registration for no gain | ~100 LOC |
| A8 | **T0 ≡ T1 bitwise as the acceptance criterion, a release blocker, "never a tolerance to widen"** | `arch:466`; executed `0014/report.md:86` (288 steps / 1440 substeps) | **Answers open question 6.** The only criterion that can validate a wiring rework — and demonstrably achievable | S (harness) |
| A9 | **`dataclasses.field(metadata={"icon_namelist_origin": ...})` + a reflective reader** | `icon/components/diffusion.py:71`; `dycore.py:209` | A shipped proof-of-concept of **exactly M2's mechanism**, applied to config. Lift as the "M2 is not speculative" citation | XS |
| A10 | **`lock.toml`** — 481-line append-only SHA-pinned provenance ledger for every borrowed constant, tolerance and field; plus the reviewer rules (re-derive every tolerance from the pinned upstream test; mutation-probe every oracle) | `development/references/lock.toml` | Tolerance provenance. Caught six silently-loosened tolerances | M |

Determinism rules worth copying with A7: hash floats as `float.hex()`, never `id()` or `hash()`,
and use `ctx.backend_name` not `repr(ctx.backend)` — a real bug they hit (`0014/report.md:77`).

## Two mechanisms we missed

**M12 — declared handoff + arity check.** Every declared producer→consumer handoff must have
exactly one consumer; 0 or ≥2 both reject. `coupling/bus.py:13`: *"a dangling tendency silently
loses physics, a double consumer double-applies it."* ~90 LOC, no runtime object — `check()` runs
once and the bus never sees data.

R1 in our doc is a requirement with no mechanism; this is the mechanism. **But it catches E1 only
under one-quantity ⇒ one-name ⇒ one-buffer (M1+M2)** — without those, `PrepAdvection.vn_traj` and
`AdvectionPrepAdvState.vn_traj` are two legitimate slots and the check is decorative. Close their
hole too: `bus.py:131` iterates publishers as a list and never checks publisher *count*, while
ICON genuinely sums multiple publishers into `ddt_*`.

**M14 — parameters as a structure distinct from state.** Tunable scheme constants (entrainment
coefficients, autoconversion thresholds) declared as a `ParamTree` separate from state, so
calibration constants are never smuggled through state fields (`contracts/properties.py:78`).
Needs **zero** JAX. Equally right for ensembles, perturbed physics and namelist provenance.

Two weaker ones, listed for completeness: **M13** ordering constraints as declared data
(`must_follow`/`must_precede`, `constraints.py:42`) — but as built it is free-form strings, so
`must_follow=("satdad",)` silently passes; needs reference-based names first. And reserving
`differentiable: native|custom|none` as a metadata key now to avoid a vocabulary break later —
one reserved key, low value, do not schedule it.

## Adopt the concept, not the code

- **The façade** (`state/facade.py:38`) — a typed struct for execution plus a *named view* for
  tooling, with separate invalidation domains. **Our doc has no analogue and needs one**: the
  debugging/monitoring/IO story is what usually drives people back to a name-keyed bucket, and
  icon4py's output is a hardcoded whitelist with no tracer path at all. Do not take the xarray
  implementation (a second metadata system), nor their tombstone `__delitem__`, which leaks.
- **Statics are a scope, not a per-component container** (`arch:133`) — metrics/interpolation
  resolved at construction, out of the per-step contract. That is the shape E5 wants. Do not copy
  their setup path: ≥3 copies per static field (`interpolation.py:100`).
- **Cadence phase is restart carry, not config** (`wrappers.py:190`) — a restart must resume
  mid-cadence bit-exactly. **This is a place ICON-sc is ahead of us**: our doc calls integration
  control state "someone else's problem", and for `ndyn_substeps_var` (mutated at runtime,
  `standalone_driver.py:441`) that is a scope error.
- **`published` boolean + a `(shape, dtype)`-keyed scratch pool** (`bind.py:1601`) — ~10 LOC,
  dedups every same-shape temporary. Legal only because *"scratch carries no state between ops"*;
  assert that, don't assume it. Their scope vocabulary is **one boolean** — our M10 is richer and
  gets no help from their design.
- **Kind / operator / cadence as three orthogonal axes** — vocabulary only. It reframes OngChia's
  per-component Jacobi/Gauss-Seidel flag usefully: the coupling operator is a *value with a
  measured convergence order*, not a flag.

## Do not adopt

| Thing | Why |
|---|---|
| **The plan compiler as a whole** (`plan/`, 2090 LOC + 1603 LOC tests) | 1732 lines exist to *dissolve a sympl/Tasmania composition tree*; icon4py has no such algebra to dissolve. Carries 42 `PlanCompileError` refusal sites and an 11-item published refusal list — a permanent "the compiler can't compile this yet" tax. Hosting **one** dycore required inventing a new hook quartet (`plan_ingress`/`plan_substep_begin`/`plan_substep_end`/`plan_egress`). Transferable residue ≈300 LOC (A7 + the scratch pool + bind-time name→arg-pack resolution) |
| **`dict[str, DataArray]` as the state type** (`vault.py` + `facade.py`, 317 LOC) | It is the run-time bucket. Their own results corroborate us: acceptance required *proving zero name lookups per step*, and they needed vault + compiler + swap variants + cadence masks + guards to recover what a typed dataclass gives free. **ICON-sc built a 1732-line compiler whose main job is erasing a dict its own T0 tier introduced. icon4py never has to introduce it** |
| **The coupling algebra** (`federations.py`, `steppers.py`, 967 LOC) | **2 of 7 combinators used** by any real preset. `jw.py:231` is `SequentialUpdateSplitting([dycore, diffusion])` = icon4py's driver order, and `jw.py:285` keeps a hand-written closure that is bitwise equivalent. Stage arithmetic allocates one array per field per stage (`steppers.py:325`), violating R10 outright |
| **The F-tier / JAX** (`functional/`, 811 LOC + 763 hand-ported graupel lines) | Not a lowering — a **second physics implementation**. `grep jax.ffi\|ffi_call\|custom_vjp` = **0 hits**; the `custom` route has zero implementations. The dycore is `differentiable: none`. It would *cost* us design: `functional_state()` abolishes component privacy (kills M10), and `CallingFrequency` lowers to running the inner component **unconditionally every step** under `jnp.where` — deleting the entire point of cadenced slow physics |
| **The halo story** — `HaloPolicy`, `halos="auto"`, the composition-time validator | **Entirely unbuilt.** `HaloState.DIRTY` appears once, as an enum member (`typing.py:55`), and is never assigned anywhere in `src/`. `HaloPolicy` appears only in definition/parsing/re-export modules. `communicates_internally=True` is declared by both real components and **read by nothing** — both delegate halos back into the icon4py granule. The architecture calls it "the single most valuable safety net"; the annotation is 8 lines and the consumer is the entire cost. Adopting it means building the unbuilt part of a prototype on the one axis where it has zero evidence, against a granule boundary the architecture itself forbids decomposing |
| **Ping-pong SSA / even-odd variants for time levels** (`bind.py:396`) | Only n=2, no `nsav`; time levels become un-nameable (`FieldHandle.name` is "debug/repr only"). **ICON-sc's own dycore opted out** and kept `nnow/nnew` component-private (`icon/components/dycore.py:663`) — the strongest available evidence the mechanism does not cover the dycore |
| **The copy-in/copy-out granule adapter** (`dycore.py:945`, `diffusion.py:472`) | 17 full-field memcpys per Δt. They pay it because T0 buffers are not pointer-stable: *"aliasing it once would be unsound"* (`microphysics.py:335`) |
| **T2 / T3** | Never built; T3's cache key is known-broken — `plan_hash` is blind to constructor parameters, so `Relaxation(tau=1)` and `Relaxation(tau=2)` hash identically. Known since S05, work unit 0022 is a `plan.md` and nothing else |
| **Process-global `names._REGISTRY` mutated at import** (`names.py:70`) | Already caused a cross-test global-state bug. A per-model registry instance is the icon4py-safe form |

Note on the zero-copy wrap (`ingress/gt4py.py:76`, `gtx_common._field(buffer, domain=...)`):
public `gtx.as_field` always copies, `_field` aliases with write-through — **verified in
icon4py's own gt4py pin**. But this is *not* an ICON-sc asset: icon4py already uses it in three
places (`bindings/icon4py_export.py:96`, `states/factory.py:93`, `solve_nonhydro.py:1030`).
What remains is the inconsistency — `DiagnosticState.surface_pressure` still uses `gtx.as_field`
and copies on every attribute read (E-adjacent, see the evidence appendix). `_field` is private
API; ICON-sc pins it via a `lock.toml` entry, which is the right way to depend on it.

## Where the prototype's simplicity is load-bearing

Five places it plausibly breaks at icon4py scale, worth knowing before borrowing:

1. **The plan compiler needs a complete front end** for every composition construct. Does not
   scale linearly in components.
2. **Cadence dissolution breaks first.** Adaptive `ratio_provider` is already a T1 refusal; CF
   under multi-stage schemes was attempted and abandoned. Real ICON has five cadences plus a
   CFL-adaptive substep ratio ∈ [5,12], and the lcm × parity fixpoint is the exposed mechanism.
3. **No write-set analysis exists.** Federation property merge is a self-described *"approximate
   union view"* where *"cross-section spec conflicts are not re-validated here"* and later
   sections silently win. Two components is auditable by eye; `NWP_FAST_ORDER` at ~11 is not.
   **ICON-sc shows the hooks are cheap and in the right place; it did not claim the prize.**
4. **~20 concepts** a physics developer must learn before the first line of physics, vs ~4 in
   icon4py today. And the contract does not remove the work: the declaration is 15 lines out of
   360 for satad; ~120 lines of granule plumbing per hosted granule is untouched, plus ~190
   hand-written name bindings per *two* granules in three unsynchronized forms.
5. **Flat string namespace in one process-global registry** — 18/72 for a 2-component model.
   Scale by tracers × tiles × time levels and the registry is the coordination bottleneck.

## Upstream icon4py findings — none ever filed

Work unit `0023-upstream-reports/` contains **only a `plan.md`**; no report, nothing filed with
C2SM. These live inside the S06–S13 step reports and are actionable independently of any design
decision here.

| ID | Finding | Status |
|---|---|---|
| **U1** | **Graupel cold-glaciation water-budget leak.** Supercooled qc at T ≲ 233 K near the moist-domain top *gains* total water. Fixed absolute amount per column, independent of qc magnitude for qc ∈ (QMIN, 3e-3]: **+1.59e-4 kg/m² per Δt=30 s** at qv_scale=1, **+1.050e-3** at 0.1; worst in-domain relative 4.32e-4. Suppressed entirely by any coexisting ice-phase seed; zero for qc ≤ QMIN | **Has a runnable, wrapper-free reproducer** on public icon4py APIs (`test_graupel_component.py::test_cold_leak_reproduces_in_bare_granule`), asserted within `(5e-5, 5e-4)` so it visibly collapses when fixed |
| **U9** | **`is_surface` index bug in the graupel scan.** `k_lev` is a scan carry starting at 0 relative to `vertical_start=kstart_moist` (`graupel_stencils.py:827`), compared at `:218` against `ground_level = num_levels-1` (absolute, `single_moment_six_class_gscp_graupel.py:299`). The surface minimum-fall-speed clamps **only ever fire when `kstart_moist == 0`** — true for WK data, false for any column grid with `kstart_moist = 2` | **Verified independently.** One line. ICON-sc replicated it verbatim for parity rather than fixing it |
| **U2** | **`wgtfacq_c` / `wgtfacq_e` shifted-K-domain footgun.** Both producers — the metrics factory and the serialbox reader — emit these as 3-level fields on K-domain `[nlev−3, nlev)`. The convention is visible **only in the factory registration** | Cost ICON-sc ~2 work units of misdiagnosis. Publish the symptom signature: *"bitwise-unequal across identical rebuilds, deviations seeded near special points"* ⇒ out-of-domain reads, not physics |
| **U3/U4/U5** | One grid-factory issue. `GridGeometry.mean_cell_area` differs from ICON's serialized value by **4e-5 relative**, deterministically → 3.6e-6 m/s on `vn` after one Δt. RBF vertex factory emits `invalid value encountered in divide` at pentagon rows. `GridManager(keep_skip_values=False)` does **not** pad file-sourced vertex tables; icon4py's own `_replace_skip_values` then makes the RBF kernel matrix **exactly singular** (`LinAlgError`), and its max-valid padding differs from the archive's in 11 of 12 pentagon rows | Latent trap for anyone building a grid from file rather than savepoint |
| **U6** | `SPECIFIC_HEAT_CAPACITY_ICE = 2108.0` vs ICON `ci = 2106.0_wp`. Live only in the temperature-dependent latent-heat-of-sublimation branch, i.e. dead under the default `use_constant_latent_heat=True` | Real, latent, exercised by no verification data |
| **U7** | satad divergence: ICON silently caps at `count < maxiter`; **icon4py raises `ConvergenceError`**. ICON 2026.04 also has `tune_supsat_limfac` and takes `w`; icon4py v0.2.0 has neither (identical under the default namelist) | Will bite the first non-default configuration |
| **U8** | The multi-substep dycore test is **MCH-only**, with a literal `# why is this not run for APE?` at `test_solve_nonhydro.py:784` | Test-coverage gap. ICON-sc measured APE two-substep `vn` deviations of 4.85e-12 / 7.19e-12 and root-caused them as *not* an orchestration bug |
| **U10** | ICON's divergence damping enters **without a `dtime` factor** — removes a fixed fraction of a 2Δx mode per substep independent of Δτ (≈82 % at the worst edge) | Numerical-design observation; matters for convergence studies |
| **U11** | `total_precipitation_flux` computed only under `do_latent_heat_nudging=True` at v0.2.0 (else exact zeros) | Exposing it as a diagnostic would mislead. Relevant to E3 |
| **U12** | icon4py xfails every `solve_nonhydro`/diffusion integration test on `embedded`; the diffusion granule cannot be *constructed* on embedded | Means "embedded as the reference tier" is unavailable for a wiring-equivalence harness |

**Order:** U1 and U9 are filable today with evidence attached. U2 is a documentation/assertion
request that would save us the identical class of bug at `factory.py:544` (E8). U3/U4/U5 file as
one grid-factory issue. U6/U7/U11 are one-liners. U8 is a test-coverage PR.
