---
title: Systematic stencil-domain over-computation audit (dycore, diffusion, advection)
author: jcanton
tags: [dycore, diffusion, tracer_advection, domains, halo-exchange, skip-values, overcomputation]
created: 2026-07-17
status: draft
---

> **TL;DR** Execute a full, evidence-based audit of every stencil invocation in
> dycore + diffusion + tracer advection to find PR#1378-class defects:
> computing where results are never consumed, and reading skip-valued (-1)
> connectivities or uninitialized inputs outside the meaningful domain.

## Problem / motivation

[icon4py PR#1378](https://github.com/C2SM/icon4py/pull/1378) found a fused
stencil (`compute_rho_theta_pgrad_and_update_vn`) computing the horizontal
pressure gradient over its full outer domain `[0, end_edge_halo_level_2)`,
while the result is only consumed on `[nudging_level_2, end_local)`. Outside
that interval, E2C holds skip values (-1) on limited-area lateral-boundary
rows and halo edges and the metric inputs (`ikoffset`/`zdiff_gradp`/
`pg_exdist`) are uninitialized → segfault on LAM with compiled backends.

Nothing guarantees this was the only instance. Comments/TODOs in the code
mention over-computation in several places but are unreliable (some outdated,
some wrong). Serial CI can never expose the halo-row class (serial grids have
empty halo zones), and the embedded backend silently wraps `-1` indices, so
green tests are not evidence of safety.

## Proposal

Run a systematic audit (in progress on icon4py branch
`stencils_domains_analysis`), producing an analysis report — fixes follow as
separate small PRs per finding. Method:

1. **Empirical ground truth first** — scripts committed with the report:
   - `connectivity_reach.py`: per grid (LAM `mch_ch_R04B09`, global
     `R02B04`, torus), dump numeric zone start/end indices, a skip-value
     census per (connectivity × zone band), and neighbor-reach lemmas
     ("E2C over edges `[LB_5, LOCAL)` lands in cells `[X, Y)`").
   - `halo_reach.py`: same census on decomposed grids (4-rank serialized
     data) — the only ground truth for halo-row skip values.
   - No claim in the report may rest on docstrings or comments; interval
     arithmetic only via these numeric dumps.
2. **Inventory**: one row per stencil invocation (~40 across
   `solve_nonhydro.py`, `velocity_advection.py`, `diffusion.py`,
   `advection*.py`): written domain, per-sub-expression connectivities
   (reduction vs direct access vs indexed offset), concat_where guards
   (horizontal vs vertical), position relative to halo exchanges.
3. **Dataflow audit**: for each output written on region W, trace all
   consumers (incl. cross-component, substep/timestep loop-carry, py2fgen
   wrappers) until overwrite or halo exchange; compute required region R by
   expanding consumer domains backward through their connectivity access
   (using the reach lemmas). Classify Delta = W \ R:
   - (i) **OOB-unsafe**: direct/indexed access via skip-valued connectivity
     or uninitialized input inside Delta (the PR#1378 class),
   - (ii) **masked-but-wasteful**: reduction-masked, result unconsumed,
   - (iii) **deliberate halo redundancy**: consumed on halo to skip an
     exchange → documented OK,
   - (iv) **undercompute**: R ⊄ W — correctness bug,
   - (v) OK.
   Verdicts qualified per grid class (LAM / global / torus / distributed).
4. **Adversarial verification**: every finding independently re-verified
   (falsification attempt: missed consumer? exchange in between?
   loop-carry?); ~20% of claimed-OK rows spot-checked.
5. **Fortran cross-check** (secondary evidence): map each ICON Fortran
   loop's `rl_start`/`rl_end` (mo_solve_nonhydro, mo_nh_diffusion,
   mo_velocity_advection, mo_advection_hflux/vflux) to icon4py zones; a
   deviation triggers a re-check, never a finding by itself.

Deliverable: `docs/development/stencil_domain_audit/report.md` on the audit
branch — master verdict table (one row per invocation) + per-finding detail
(producer file:line, W, consumers file:line, R, delta, risk class, grid
classes affected, backend sensitivity, suggested fix shape) + evidence files.

## Alternatives considered

- Fix-as-you-go on a single branch: rejected — findings need review one by
  one (PR#1378 itself changed numerics validation tolerances), and a huge
  mixed branch is unreviewable.
- Pure LLM domain-restriction with test feedback (see conflicts below):
  complementary, but test-green is a weak oracle here (embedded backend
  wraps -1; serial grids hide halo rows), so this audit grounds claims in
  connectivity data + consumer tracing instead.

## Open questions / conflicts

- **Overlaps with [[personal/iomaganaris/domain-minimalization|Verify that the domains of all the GT4Py programs are as minimal as possible using an LLM]]**
  (same motivation, PR#1378; created the same day). That note proposes an
  agentic loop that restricts domains and validates via tests; this one is
  the executed audit with empirical evidence and a report-first deliverable.
  They compose: the audit's verdict table is exactly the work-list (and the
  oracle) an automated domain-minimization loop would need. The open
  question raised there — whether GT4Py domain inference could do this
  automatically if the frontend carried the missing information — applies
  here unchanged: every class-(ii) finding is a data point for what
  inference currently cannot see.
- GT4Py temporaries are computed over the full buffer regardless of the
  outer domain (`base.py` `_replace_skip_values` rationale), so even a
  perfectly restricted program domain does not eliminate skip-value reads in
  temporaries. How should findings of that shape be fixed — concat_where
  guards (PR#1378 style), `keep_skip_values=False`, or GT4Py-side domain
  inference?
- Distributed halo redundancy is sometimes deliberate (compute on halo to
  skip an exchange, e.g. advection's even-timestep vertical transport).
  Distinguishing class (ii) from (iii) requires knowing which exchanges the
  team considers cheaper than redundant compute — needs discussion per
  finding. Related: [[personal/msimberg/cleanup-distributed-computation|Cleanup the "decomposition" directory]].
