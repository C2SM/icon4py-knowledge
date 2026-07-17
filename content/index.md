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

### havogt

- [[personal/havogt/declarative-testing-harness/declarative-testing-harness|Declarative testing harness]] — keywords: testing, verification, serialbox, stencil-tests, datatests, pytest, tolerances, benchmarking

### iomaganaris

- [[personal/iomaganaris/standalone-driver-startup-opt|Optimize the startup of the standalone-driver]] — keywords: standalone-driver, driver, GPU, optimization
- [[personal/iomaganaris/domain-minimalization.md|Verify that the domains of all the GT4Py programs are as minimal as possible using an LLM]] - keywords: dycore, diffusion, tracer_advection, autoresearch

### msimberg

- [[personal/msimberg/revive-components/revive-components|Revive components]] — keywords: components, model-state, protocol, interface, design
- [[personal/msimberg/cleanup-distributed-computation|Cleanup the "decomposition" directory]] — keywords: decomposition, distributed-computation, mpi, halo-exchange, reductions, naming, refactoring

<!-- Add new contributor subsections here as needed.

### <github-handle>

- [[personal/<handle>/<slug>|Title]] — keywords: keyword1, keyword2

-->
