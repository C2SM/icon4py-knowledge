---
title: Revive components
author: msimberg
tags: [components, model-state, protocol, interface, design, field-registry, states, inputs-outputs]
created: 2026-07-13
status: draft
---

> **TL;DR** Revive and flesh out the `Component` Protocol from `model/common/src/icon4py/model/common/components/components.py` into a usable, well-documented interface for model building blocks.

> **Current direction (2026-09):** two active specs. The **v4 spec** re-specifies proposal parts 1 and 2 (the component, its inputs and outputs: quantity registry, declaration aliases, `Component` with `Input`/`Output` slots, states, gather/apply) and supersedes v3's Component contract and field metadata. The **v3 spec** (directed-graph composition layer above the `Component`: chaining, looping, branching, I/O as a sink, D0 -> D1 -> D2 -> D3 layering; D3 is a non-breaking addition, not a fork) remains the reference for composition and is unchanged by v4. NOT FROZEN.

## Problem / motivation

The codebase already defines a `Component` Protocol ([[https://github.com/C2SM/icon4py/blob/main/model/common/src/icon4py/model/common/components/components.py|components.py]]) that declares the shape a model component should have: typed inputs and outputs with CF metadata, and a `__call__` that transforms model state. However, it is currently a stub: the abstract methods (`inputs_properties`, `outputs_properties`) are unimplemented, the open TODOs are unresolved, and no concrete components in the codebase adopt the protocol.

Without a concrete protocol to follow, component code drifts into ad-hoc interfaces, making it harder to compose, test, and validate model building blocks.

## Proposal

A stub. The intent is to take the existing skeleton and:

1. Resolve the open TODOs (unit-consistency hooks, dimension checks, state interface improvements)
2. Provide a reference implementation that concrete components can inherit from
3. Define how components declare and validate their input/output contracts at runtime or type-check time

## Alternatives considered

Not yet evaluated. This is a placeholder to start the discussion.

## Open questions / conflicts

- How does this relate to the existing driver orchestration? Should components be independently runnable, or only as part of a composed pipeline?
- The TODO in `components.py:74` questions whether outputs should be split by type (tendencies, diagnostics, prognostics). This needs a design decision before the protocol is finalized.
- The TODO in `components.py:97` asks whether passing the entire state is the right interface. Alternatives include scoped state views or explicit field descriptors.

## Appendices

- [[personal/msimberg/revive-components/revive-components_spec_v4|SPEC v4 (the component, its inputs, and its outputs)]] - current proposal for parts 1 and 2: quantity registry, declaration aliases, `Component` with `Input`/`Output` slots, states (owner vs view), gather/apply defaults, explicit allocation, composite components, coupling-mode requirements. Supersedes v3's Component contract and field metadata. **NOT FROZEN.**
- [[personal/msimberg/revive-components/revive-components_spec_v3|SPEC v3 (composition layer)]] - the reference for the composition layer: a directed-graph composition layer above the `Component`, with a D0->D1->D2->D3 layering and concrete worked examples for the standalone driver, physics driver, dycore sub-stepping, and tracer advection. **NOT FROZEN.**
- [[personal/msimberg/revive-components/revive-components_spec|SPEC v2 (superseded)]] - earlier per-component frozen input/output dataclasses proposal. Superseded by v3; kept as history.

## Related documents

- [[personal/Yilu/physics-interface-current-design|Physics interface - current design (as built on physics_driver_tmx)]] - the as-built two-layer physics state on the PR #1436 stack; the precedent v4 builds on (expressibility envelope), with a supersession table in v4.
- [[personal/OngChia/physics-driver-and-components|Physics driver and component design]] - related component protocol design; v4's superseded-from-precedents table covers the overlap.
