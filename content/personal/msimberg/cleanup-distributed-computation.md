---
title: Cleanup the "decomposition" directory
author: msimberg
tags: [decomposition, distributed-computation, mpi, halo-exchange, reductions, naming, refactoring]
created: 2026-07-16
status: draft
---

> **TL;DR** The `icon4py.model.common.decomposition` package has outgrown its name: it mixes grid decomposition, MPI runtime, halo exchanges, global reductions, and single-node fallbacks. We should reorganize it around the broader concept of distributed computation.

## Problem / motivation

`model/common/src/icon4py/model/common/decomposition` currently contains several distinct concerns that are only loosely related to "decomposition" in the grid sense:

- Grid decomposition algorithms (`MetisDecomposer`, `SingleNodeDecomposer`).
- Halo geometry construction (`IconLikeHaloConstructor`, `NoHalos`).
- Distributed exchange / halo exchange runtime (`ExchangeRuntime`, `GHexMultiNodeExchange`, `SingleNodeExchange`).
- Global reductions (`Reductions`, `GlobalReductions`, `SingleNodeReductions`).
- Process topology and MPI communicator handling (`ProcessProperties`, `MPICommProcessProperties`, `init_mpi`).
- Run-type dispatching and single-node vs multi-node abstractions (`RunType`, `SingleNodeRun`, `MultiNodeRun`).

The directory name and file names (e.g. `mpi_decomposition.py`, `definitions.py`) do not reflect this breadth, making it hard to discover where a given concept lives.

## Ideas to explore

- Rename the package and files to reflect "distributed computation" rather than only "decomposition".
- Split `definitions.py` and `mpi_decomposition.py` into smaller modules grouped by concern: decomposition, halo geometry, distributed exchange, reductions, process/runtime setup.
- Separate MPI-specific code from generic protocols and single-node fallbacks more clearly.
- Reconsider whether grid decomposition belongs under the same package as MPI runtime utilities.
- Clarify naming around `DecompositionInfo` — it carries halo and ownership information, not just decomposition output.
- Revisit `ExchangeRuntime` as a generic distributed communication abstraction; evaluate if halo exchange and reductions should share a runtime surface.
- Consolidate single-node vs multi-node dispatch patterns (`get_runtype`, `create_exchange`, `create_reduction`, `get_process_properties`) in one place.

## Open questions / conflicts

- What is the right top-level name? `distributed`? `parallel`? `distributed_runtime`?
- Should halo construction live with grid utilities or with distributed communication?
- How much of this overlaps with planned component / model-state cleanup? See [[personal/msimberg/revive-components|Revive components]].
