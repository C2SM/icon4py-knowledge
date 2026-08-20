---
title: Physics interface — discussion points
author: Yilu
tags: [components, physics-driver, protocol, forcing-mode, coupling, metadata, io, design]
created: 2026-08-07
status: draft
---

> **TL;DR** Open questions about the physics interface that came out of building the
> muphys + TMX integration (see
> [[personal/Yilu/physics-interface-current-design|the as-built reference]]), collected
> as an agenda for the team design discussion. Each point has context, the question,
> and a suggested position. Several intersect with
> [[personal/OngChia/physics-driver-and-components|OngChia's physics-driver proposal]] —
> flagged where they do.

## A · Driver semantics

### A1. Process coupling: sequential (as built) vs accumulate-then-apply

**Context.** The driver applies each process's forcing *inside* the process loop, so a
later process gathers the already-updated state (muphys' condensation heating is seen by
TMX's stability calculation). This is sequential, Gauss-Seidel-style coupling — and it is
what ICON `mo_aes_phy_main` does: the reference `tmx-entry` savepoints contain the
*post-graupel* state, so our validation data encodes this ordering.

**Question.** Do we ever want an accumulate-all-tendencies, apply-once-at-the-end mode
(Jacobi coupling)? It would buy a single accumulated `ddt_phy` handback to the dycore
and process independence — but it *changes the physics* (first-order in dt, not
roundoff) and would need a matching reference run to validate against.

**Suggested position.** Keep sequential as the only mode for now (port fidelity; the
savepoints require it). Treat Jacobi as a deliberate future physics decision, not a
refactor. *(Overlaps the Jacobi/Gauss-Seidel axis in OngChia's proposal.)*

### A2. Split `scatter_to_prognostic` into apply vs store

**Context.** Scatter currently does two jobs in one call: apply tendencies to the
prognostic state AND store the process diagnostics (muphys precip, TMX km/kh/heating) on
the process state. This double duty is the reason `ForcingMode.DIAGNOSTIC` cannot be
implemented today — skipping scatter would also discard the diagnostics.

**Question.** Split the protocol method into `apply_tendencies(prognostic, outputs,
dtime)` + `store_diagnostics(outputs)`, with the driver calling both back-to-back?
Behavior-preserving, small (protocol + muphys + tmx); gives `kind` a real dispatch role
(B2) and pre-shapes any A1 evolution. (With A3 decided as removal, this is no longer
urgent for any mode switch — it stands on its B2/A1 merits alone.)

**Suggested position.** Yes, but as its own small PR against main *after* the team
agrees — the protocol and muphys are merged main code now; churning them from a feature
branch is the wrong vehicle.

### A3. `ForcingMode.DIAGNOSTIC` — **DECIDED 2026-08-07: removed**

**Context.** `PhysicsProcess.forcing_mode` existed as the analogue of AES `fc_xxx`
switches, defaulted to `APPLY`, and the driver raised `NotImplementedError` for anything
else. Nothing used DIAGNOSTIC.

**Decision (Yilu + colleague).** Confusing and currently useless — the whole
`ForcingMode` concept (enum, field, guard) is removed via a small standalone PR against
main (branch `remove_forcing_mode`). If a compute-without-applying mode is ever needed
(e.g. validating radiation in-loop against a fixed trajectory), it returns *with* an
implementation, on top of the A2 scatter split — component-level savepoint datatests
cover that use case today.

## B · Contracts and metadata

### B1. The state↔component contract is enforced by nothing

**Context.** `Component` declares `inputs_properties`/`outputs_properties`;
`PhysicsState.as_component_input()` returns a dict the component picks inputs from by
name. That the dict's keys cover the declared inputs is a per-process convention — the
driver never checks it (one TMX unit test does).

**Question.** Should the driver validate (completeness, and eventually units/dims) at
registration time or per step? *(This is the gap OngChia's StateView/consistency-check
design targets.)*

**Suggested position.** At minimum a cheap registration-time completeness check in
`PhysicsDriver.__init__` — fail at construction, not at step N. Full metadata
interpretation is a bigger design (see B2) and belongs with OngChia's proposal.

### B2. `kind` tags: half-populated, never read

**Context.** As-built audit finding: the 7 TMX tendency outputs inherit
`kind="tendency"` from the shared `tendency_of()` helper; the 8 diagnostics carry no
`kind` at all; and no code path reads the tag — the tendency/diagnostic split is done by
dataclass-field membership in the component.

**Question.** Make `kind` real (populate everywhere, have scatter/driver dispatch on it)
or drop it from the metadata?

**Suggested position.** Tie to A2/B1: if scatter splits into apply/store, `kind` is the
natural dispatch key and should become mandatory; if not, remove it rather than keep a
half-truth in the metadata.

### B3. Output naming — **DECIDED 2026-08-07: `tend_*` on the wrapper contract**

**Decision.** The component contract speaks `tend_*` uniformly (matching muphys and
ICON-AES's own `tend%` structure); done in PR #1360 by renaming the TMX wrapper's output
keys. Granules keep their internal port names (upstream Tmx stays `ddt_*`); the
component adapter owns the translation (`TENDENCY_GRANULE_PORTS` in tmx `data.py`) —
which also made the previously-implicit tendency/diagnostic split explicit.

### B4. Field passing is dict-of-references

**Context.** `as_component_input()` hands out references to state-owned buffers; the
component writes into component-owned output buffers; no copies anywhere. Efficient, but
nothing stops a component from mutating an input (the muphys granule famously mutates
in place — its component copies inputs deliberately).

**Question.** Document "inputs are read-only by convention" and leave it, or introduce
an enforcement/ownership notion (e.g. in a future StateView)?

**Suggested position.** Document the convention now (one paragraph in the protocol
docstrings); revisit enforcement with OngChia's proposal.

### B5. Where does field metadata live? — proposed rule, applied in #1360

**Context.** Precedent was mixed: muphys' precip attributes went into the common
registries with a single consumer, while `dz` and TMX's interface fields stayed local
in the component's `data.py`.

**Proposed rule (please confirm):** *promote to `common` when a second consumer
appears, or when the quantity is clearly model-wide vocabulary; keep
component-interface quirks local.* Applied in #1360: the four surface-flux fields
moved to a new `SURFACE_FLUX_CF_ATTRIBUTES` registry in `common/states/data.py`
(model-wide — future JSBACH coupling and output both want them, mirroring how precip
was handled in #1301); `pressure_ifc`, `air_mass`, `cv_air`, `q_snocpymlt` stay local
(`air_mass` is the nearest future promotion candidate — advection already computes the
same quantity).

## C · Integration gaps

### C1. Physics diagnostics never reach the output files

**Context.** The NetCDF writer stores prognostics + driver-computed diagnostics (u/v,
pressure). Muphys precip fluxes and TMX km/kh/heating/vertical integrals stay on their
process states — computed every step, visible to nobody.

**Question.** What is the IO hook for per-process diagnostics? (Driver iterates
processes and asks for storeable fields? Processes register DataArrays with the
IO monitor at init?)

**Suggested position.** Needed before any scientific use of the APE run; design it
once, for all processes — a `PhysicsState`-level `output_fields()` accessor mirroring
`as_component_input()` would fit the existing pattern.

### C1b. Duplicate diagnostics between process gathers

**Context.** Muphys' gather diagnoses `te`/`p`; after muphys' scatter updates the state,
TMX's gather re-diagnoses `T`/`T_v`/`p`/`p_ifc` — same shared stencils, run twice per
step. Most of the recomputation is *semantically required* under sequential coupling
(muphys changed exner/theta_v, so TMX must see the updated values); the duplication is
the price of per-process self-sufficiency, and the cost is pointwise stencils — small
next to the granules' solves.

**Questions.** (1) Fidelity, to check before v07 validation: does ICON re-diagnose
pressure between graupel and vdf, or hold the step-start pressure fixed across the
fast-physics sequence? (2) Architecture: a shared driver-level diagnostic state
(diagnose once, processes consume + update) needs to know which diagnostics are stale
after each scatter — which is exactly the per-field freshness metadata in
[[personal/OngChia/physics-driver-and-components|OngChia's StateView proposal]] and the
shared registry in [[personal/jcanton/model-state/model-state|model-state]]. This is
the concrete benchmark case for those designs.

**Suggested position.** Keep per-process self-sufficiency for now (correct by
construction, cheap); treat this as the motivating workload when the StateView /
model-state discussion happens, not as a standalone optimization.

### C2. Inter-process data handoff

**Context.** The protocol has none: processes communicate only through the prognostic
state. The TMX surface fluxes were therefore built as a provider seam *inside*
`TmxState` (zero-flux now) rather than as a Component ordered before TMX — a driver-level
handoff mechanism for a zero-writing provider was not warranted.

**Question.** Radiation will likely force this (its heating rates feed vdf in AES; its
inputs include cloud state from microphysics). General mechanism, or keep solving it
per-case with seams?

**Suggested position.** Keep per-case seams until radiation's actual data flow is on the
table; design the general mechanism against a real second consumer, not speculatively.

### C3. TMX enablement: opt-in vs experiment-gated

**Context.** Muphys auto-enables from the experiment namelist (`aes_phy_nml` present);
TMX is opt-in only (`ExperimentConfig.tmx` defaults `None`, injected explicitly in
tests). Deliberate while the v06 reference cannot validate a TMX-on run.

**Question.** Once v07 (with tmx savepoints) becomes the reference: should TMX
auto-enable from the namelist (e.g. `aes_vdf_nml` presence / `dt_vdf > 0`) exactly like
muphys?

**Suggested position.** Yes — symmetric gating once the reference validates it; keep the
opt-in override for experiments.

### C4. Ocean bulk-flux provider (the next TMX step)

**Context.** Surface fluxes are zero behind the `SurfaceFluxProvider` seam. The real
scheme for the aquaplanet is the open-water branch only: prescribed constant SST
(303.15 K), `compute_sfc_roughness` → Louis exchange coefficients
(`sfc_exchange_coefficients`, mo_vdf_diag_smag.f90) → `q_sat(SST)` →
`compute_sfc_fluxes` (mo_tmx_surface.f90). No land/JSBACH, no sea ice.

**Question.** Scope + interface: which inputs does `compute()` need (lowest-level state,
SST, roughness); where does SST configuration live; validated against the
`tmx-surface-fluxes` savepoints (v07).

**Suggested position.** This is its own design session once the surface scheme is
understood — the seam means nothing else needs to change.
