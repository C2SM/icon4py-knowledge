---
title: Glossary
description: "The shared vocabulary of icon4py design discussion — one term, one meaning, used in proposals, review, and code."
tags: [glossary, vocabulary, ubiquitous-language, naming, terms]
---

The vocabulary this repository argues in. One term, one meaning. If a proposal needs a
word that is not here, add it in the same pull request; if it needs a word that is here
to mean something else, that is a conflict — see *Contested terms*.

Terms borrowed from ICON, GT4Py, or CF conventions keep their upstream meaning unless
this file says otherwise, and any departure is stated explicitly.

This first version records only terms whose meaning is **not** inferable from ordinary
English or from general programming usage — the ones where a newcomer's first guess is
wrong. Everyday words used in their everyday sense are deliberately absent. Entries are
grouped by where the word comes from, because that is what decides who owns its
meaning: we may not redefine a GT4Py or CF term, but icon4py's own terms are ours to
settle.

## Terms

### From GT4Py

| Term | Meaning | Anchored in |
|---|---|---|
| Field | The array-like value GT4Py computes on, defined over named dimensions — the *container*, not the physical quantity it holds. A meteorological field is a quantity; a GT4Py `Field` is the data structure. | GT4Py; aliases in `model/common/.../field_type_aliases.py` |
| Dimension | A **named** axis — `Cell`, `Edge`, `Vertex`, `K` — not a count of axes. "Two-dimensional" says nothing about which two. | `common/dimension.py` |
| Local dimension | A dimension that indexes a fixed-size neighbour list rather than a grid location: `E2CDim` ranges over the cells adjacent to an edge. Declared `DimensionKind.LOCAL`. | `common/dimension.py` |
| Sparse field | A field carrying a local dimension. Unrelated to sparse matrices — the data is dense; the *indexing* is by neighbour. | `common/dimension.py` |
| Skip value | The sentinel `-1` in a connectivity, marking a neighbour that does not exist — e.g. an edge on a limited-area lateral boundary with only one adjacent cell. Reading through one yields undefined data unless the computation masks it. | [[personal/jcanton/stencil-domain-audit\|Stencil-domain audit]] |
| Field offset | A named shift to a neighbour or to another vertical level: `E2C` (edge to its cells), `Koff` (level to level). | `common/dimension.py` |
| Offset provider | The mapping handed to a program at call time that resolves each field offset to the connectivity realising it. Not a provider in the dependency-injection sense. | `common/model_options.py` |
| Field operator | A GT4Py function computing fields from fields. Not an operator in the mathematical sense, nor a Python operator. | `@gtx.field_operator` |
| Program | A GT4Py **entry point**: it calls field operators over an explicit domain and writes into pre-allocated output fields. A single compiled kernel, not a program in the ordinary sense. | `@gtx.program` |
| Stencil | Informally, one ICON computation ported to GT4Py — usually realised as one program. Used loosely and near-interchangeably with *program* in prose. | [[personal/jcanton/stencil-domain-audit\|Stencil-domain audit]] |
| Domain | The index range a program computes over, as `(dimension, start, end)`. **Not** the problem domain and not the model's physical domain. Over-wide domains are a recurring defect class. | [[personal/jcanton/stencil-domain-audit\|Stencil-domain audit]] |
| Backend | The compilation target a program is built for — `gtfn_cpu`, `gtfn_gpu`, a DaCe backend. Nothing to do with server-side software. `None` means embedded. | `common/model_backends.py` |
| Embedded | Executing GT4Py code by interpreting it in Python instead of compiling it, for debugging and for operators that cannot be compiled. Nothing to do with embedded systems. | `common/states/factory.py` |

### From ICON and meteorology

| Term | Meaning | Anchored in |
|---|---|---|
| Prognostic variable | A variable carried forward by the time integration — it is *state*. In icon4py's dycore: `vn`, `theta_v`, `exner`, `rho`, `w`. Unrelated to prediction quality or to the medical sense. | [[personal/OngChia/physics-driver-and-components\|Physics driver and components]]; `solve_nonhydro.py` |
| Diagnostic variable | A variable *derived* from prognostics at a given instant and not integrated in time — pressure, temperature. Carries no history. Again not the medical sense. | [[personal/OngChia/physics-driver-and-components\|Physics driver and components]] |
| Tendency | A contribution to the time rate of change of a prognostic variable, returned by a component and applied by whatever advances the state. Not an inclination or a trend. | [[personal/OngChia/physics-driver-and-components\|Physics driver and components]] |
| Full level | A vertical level at the centre of a layer, where most prognostic variables live. | `common/grid/vertical.py` |
| Half level | A vertical level at a layer *interface*, where vertical velocity and fluxes live — not "half of a level". Field metadata records it as `is_on_half_levels`. | `common/states/model.py` |
| Zone | A named region of the horizontal index space, not a geographic area: `INTERIOR`, `LATERAL_BOUNDARY[_LEVEL_n]`, `NUDGING`, `HALO[_LEVEL_n]`, `LOCAL`, `END`. Computation ranges are expressed in zones rather than raw indices. | `common/grid/horizontal.py` |
| Halo | Grid points a process holds a copy of but does not own, kept current by exchange with the owning process. Not a ring or an aura. | `common/decomposition/definitions.py` |
| Nudging | The zone of a limited-area domain where the solution is relaxed toward driving data from a coarser model. A specific region and procedure, not "gentle adjustment" in general. | `common/grid/horizontal.py` |
| Granule | A major ICON code unit ported to icon4py as a self-contained, usually stateful object — `solve_nonhydro`, `diffusion`, the microphysics schemes. A unit of *porting*, not a small particle. | `standalone_driver/driver_utils.py` (`Granules`) |
| Dycore | The dynamical core: the non-hydrostatic solver advancing the resolved flow, as opposed to the parameterized physics. | `model/atmosphere/dycore/` |
| Savepoint | A labelled dump of ICON's Fortran state at one point in one run, written by Serialbox and read back as reference data. Not a database savepoint and not a checkpoint the model can restart from. | `model/testing/serialbox.py` |
| Datatest | A test that runs icon4py against serialized ICON reference data from savepoints, as opposed to a unit or stencil test. | [[personal/havogt/declarative-testing-harness/declarative-testing-harness\|Declarative testing harness]] |

### From icon4py

| Term | Meaning | Anchored in |
|---|---|---|
| Field factory | The setup-time machinery that computes derived fields on demand from other fields and records their metadata, rather than allocating everything up front. `FieldSource` and `FieldProvider` are its protocols. | `common/states/factory.py` |
| Decomposition | The split of the grid across MPI ranks, and the ownership information that comes with it — which points a rank owns and which are halo. Not decomposition in the general design sense. | `common/decomposition/` |
| Driver | The executable that builds the grid and initial state and runs the time loop. Not a device driver. `standalone_driver` is the one that does not require ICON's Fortran. | `model/standalone_driver/` |
| Orchestration | A driver's sequencing of components within a timestep — call order, call frequency, how each sees the state. See *Deprecated aliases* for the older, incompatible sense. | [[personal/OngChia/physics-driver-and-components\|Physics driver and components]] |
| Monitor | A protocol for components that observe or store state rather than change it — the IO path. Not monitoring in the operational sense. | `common/components/monitor.py` |
| py2fgen | The tool generating Fortran bindings so that ICON's Fortran can call into icon4py. The direction is Fortran-calls-Python. | `tools/src/icon4py/tools/py2fgen/` |

### From CF conventions

| Term | Meaning | Anchored in |
|---|---|---|
| Standard name | A string from the controlled CF vocabulary identifying *what physical quantity* a field holds, independent of its variable name in code. Required field metadata; it is what lets a component ask for an input by meaning rather than by name. | `common/states/model.py` (`RequiredMetaData`) |
| Units | The CF units string for a field, carried as required metadata and checkable at component boundaries. Not free-form documentation. | `common/states/model.py` (`RequiredMetaData`) |

## Deprecated aliases

Words that used to mean a term above, kept so that search still finds old documents.

| Alias | Use instead | Why it changed |
|---|---|---|
| Orchestration *(DaCe sense)* | *(no current term)* | Once meant compiling a sequence of GT4Py programs as one dataflow graph. That machinery was removed from icon4py as "outdated and unmaintained"; DaCe survives only as a backend. In current documents *orchestration* means a driver sequencing components. Evidence: [[personal/jcanton/model-state/model-state_evidence\|model-state evidence]] |

## Contested terms

Terms whose meaning is genuinely open between proposals. Do not resolve these here —
record each meaning and what would settle it, and raise it in the proposals themselves.

### _component_

The most expensive collision in the repository: four open designs use the word for
things with incompatible signatures, and each reads as if it were the only one.

| Meaning | Document | Author |
|---|---|---|
| Any self-contained module consuming model state and producing tendencies or state updates — including forcings and boundary-condition updates, not only parameterizations | [[personal/OngChia/physics-driver-and-components\|Physics driver and components]] | OngChia |
| A typed `Protocol[InputT, OutputT]` with `run(state: InputT, dtime) -> OutputT`, frozen dataclasses both ways | [[personal/msimberg/revive-components/revive-components\|Revive components]] | msimberg |
| A callable taking one shared `ModelState` and writing in place: `__call__(state, step: StepInfo) -> None` | [[personal/egparedes/layered-architecture-refactor\|Layered architecture refactor]] | egparedes |
| A callable over dictionaries: `__call__(dict[str, DataField], datetime) -> dict` | icon4py PRs 1301 / 1360, surveyed in [[personal/jcanton/model-state/model-state\|Model state]] | — |

There is also an existing `Component` protocol in `common/components/components.py` that
several of these claim to extend or replace.

**What would settle it:** agreement on the requirements in
[[personal/jcanton/model-state/model-state|Model state]], which argues the four cannot
be reconciled until the design states what it must achieve. Until then, a document
using *component* should say which signature it means.

### _model state_ / _state_

The same disagreement seen from the data side: what the thing components read from
actually is.

| Meaning | Document | Author |
|---|---|---|
| A setup-time wiring step emitting ordinary typed dataclasses — not a run-time container at all | [[personal/jcanton/model-state/model-state\|Model state]] | jcanton |
| One shared `ModelState` object passed around and written in place | [[personal/egparedes/layered-architecture-refactor\|Layered architecture refactor]] | egparedes |
| A run-time `StateView` over a `StateProvider`, with per-field freshness metadata | [[personal/OngChia/physics-driver-and-components\|Physics driver and components]] | OngChia |
| Typed frozen dataclasses constructed per call, no shared container | [[personal/msimberg/revive-components/revive-components\|Revive components]] | msimberg |
| A per-process `PhysicsState` gather/scatter adapter | icon4py PRs 1301 / 1360, surveyed in [[personal/jcanton/model-state/model-state\|Model state]] | — |

**What would settle it:** the same decision as *component* — these are one question, and
[[personal/jcanton/model-state/model-state|Model state]] proposes taking the
requirements first.

### _step_

| Meaning | Document | Author |
|---|---|---|
| A composable unit of execution over a shared `Carry`, with combinators (`when`, `branch`) | [[personal/msimberg/revive-components/revive-components\|Revive components]] spec v3 | msimberg |
| Information about the current time step, passed to a component as `StepInfo` | [[personal/egparedes/layered-architecture-refactor\|Layered architecture refactor]] | egparedes |
| The model timestep itself, in ordinary prose across most documents | — | — |

**What would settle it:** whichever component design is adopted. A document meaning the
timestep should prefer *timestep* and leave *step* to the composition sense, or say
which it means.
