---
title: icon4py Knowledge Base
---

Design ideas and proposals for [icon4py](https://github.com/C2SM/icon4py). Drop
an idea, cross-check it against what already exists, and surface conflicts early.

This index is the map of everything here. Each entry lists **keywords** for the
topics a document discusses — scan them to find overlapping or conflicting ideas.
See `AGENTS.md` in the repository root for how to add a proposal and keep this
index current. (Keep entries and their keywords in sync with each document's `tags`.)

## Shared

Proposals the group broadly agrees are implementation-ready.

_None yet._

<!-- Entry format:
- [[shared/<slug>|Title]] — keywords: keyword1, keyword2, keyword3
-->

## Personal

Work-in-progress proposals, organized by contributor.

### egparedes

- [[personal/egparedes/layered-architecture-refactor|Layered architecture: analysis and refactoring proposal]] — keywords: architecture, layers, tach, packaging, refactoring, components, protocol, model-state, tendencies, field-factory, registry, grid, domain, decomposition, testing, validation, serialbox, py2fgen, bindings, config, precision, io

### havogt

- [[personal/havogt/declarative-testing-harness/declarative-testing-harness|Declarative testing harness]] — keywords: testing, verification, serialbox, stencil-tests, datatests, pytest, tolerances, benchmarking

### iomaganaris

- [[personal/iomaganaris/standalone-driver-startup-opt/standalone-driver-startup-opt|Optimize the startup of the standalone-driver]] — keywords: standalone-driver, driver, GPU, optimization
- [[personal/iomaganaris/domain-minimalization.md|Verify that the domains of all the GT4Py programs are as minimal as possible using an LLM]] - keywords: dycore, diffusion, tracer_advection, autoresearch
- [[personal/iomaganaris/specialize-domain-bounds.md|Specialize GT4Py programs with runtime-varying domain bounds via the variants parameter]] - keywords: dycore, diffusion, tracer_advection, setup_program, gt4py, performance, specialization

### jcanton

- [[personal/jcanton/stencil-domain-audit|Systematic stencil-domain over-computation audit]] — keywords: dycore, diffusion, tracer_advection, domains, halo-exchange, skip-values, overcomputation
- [[personal/jcanton/jsbach-port/jsbach-port|Porting ICON-Land (JSBACH) to icon4py / GT4Py — plan & scope]] — keywords: jsbach, icon-land, land-surface, gt4py, port, tmx, aes, validation, oracle, sse
- [[personal/jcanton/model-state/model-state|Model state]] — keywords: state, model-state, components, fields, registry, metadata, duplication, allocation, lazy-evaluation, labels, halo-exchange, restart, icon-sc, contracts, prior-art
- [[personal/jcanton/model-state/model-state-v2-distillation|Model state — v2 distillation]] — keywords: state, model-state, components, fields, registry, metadata, duplication, allocation, labels, halo-exchange, restart, icon-sc, contracts, prior-art, constraints, goals

### msimberg

- [[personal/msimberg/revive-components/revive-components|Revive components]] — keywords: components, model-state, protocol, interface, design
- [[personal/msimberg/cleanup-distributed-computation|Cleanup the "decomposition" directory]] — keywords: decomposition, distributed-computation, mpi, halo-exchange, reductions, naming, refactoring
- [[personal/msimberg/checkpoint-restart/checkpoint-restart|Checkpoint/restart]] — keywords: checkpoint, restart, io, state, serialization, netcdf, dycore, distributed

### OngChia

- [[personal/OngChia/physics-driver-and-components|Physics driver and component design]] — keywords: components, physics-driver, protocol, design
- [[personal/OngChia/scientific-validation|Scientific test cases for icon4py]] — keywords: testing, test-cases, scientific-validation, dycore, physics, benchmarking


<!-- Add new contributor subsections here as needed.

### <github-handle>

- [[personal/<handle>/<slug>|Title]] — keywords: keyword1, keyword2

-->
