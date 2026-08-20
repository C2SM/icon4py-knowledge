---
title: Physics interface — discussion points
author: Yilu
tags: [components, physics-driver, protocol, coupling, metadata, io, design]
created: 2026-08-07
updated: 2026-08-20
status: draft
---

> **TL;DR** The original agenda (2026-08-07) collected 13 open questions from the
> muphys + TMX integration. The parallel-coupling redesign of 2026-08-18/19 and the
> v08 validation of 2026-08-20 resolved most of them — the outcomes are documented in
> [[personal/Yilu/physics-interface-current-design|the as-built reference]].
> This page keeps only the points still open.

## Open points

### B1. Input-contract validation

**Context (updated).** The output side is now enforced by construction — the driver
routes on `outputs_properties`. The *input* side is still a convention: that
`as_component_input()` keys cover the component's `inputs_properties` is checked by
one tmx unit test, not by the driver.

**Question.** Cheap registration-time completeness check in `PhysicsDriver.__init__`
(fail at construction, not at step N)? Units/dims interpretation stays with
[[personal/OngChia/physics-driver-and-components|OngChia's proposal]].

**Suggested position.** Yes to the completeness check — a few lines, zero step-time
cost.

### B4. Read-only by convention

**Context (updated).** Pointers everywhere, by design: the façade binds model-state
pointers and `as_component_input()` returns references. The frozen-entry invariant is
now *tested* (the entry state must be bitwise untouched until apply) — but nothing
*enforces* that a component doesn't mutate an input at runtime.

**Question.** Document-and-trust (protocol docstrings now state it), or an
enforcement/ownership notion in a future StateView?

**Suggested position.** The tested invariant + docstrings are proportionate for now;
revisit with OngChia's proposal.

### C1. Physics diagnostics → output files

**Context (updated, simpler than before).** All per-process diagnostics now land in
one place — `driver.diagnostics[process][name]`, ICON `field%` spirit — instead of
being scattered across process states. The IO hook design reduces to: walk that dict,
wrap fields as DataArrays, register with the IO monitor.

**Question.** Hook it into the NetCDF writer at init (names from
`outputs_properties` metadata) — when the APE run needs scientific output.

**Suggested position.** Straightforward now; schedule with the first scientific use.

### C4. Ocean bulk-flux provider

**Context (updated, downgraded from blocker to refinement).** The v08 validation
showed the zero-flux residual is ~0.3 % relative (theta_v) and below — the 11.3 K gap
previously attributed to the missing fluxes was mostly granule/coupling issues, since
fixed. The seam is unchanged: open-water branch only, prescribed SST 303.15 K,
`compute_sfc_roughness` → Louis exchange coefficients → `q_sat(SST)` →
`compute_sfc_fluxes` (mo_tmx_surface.f90).

**Question.** Scope + interface as before — plus the clean validation experiment:
a reference run *without* surface fluxes would isolate the pure coupling error
(expected: residuals drop to the noise tier everywhere).

**Suggested position.** Own design session; nothing else blocks on it.
