---
title: Revive components
author: msimberg
tags: [components, model-state, protocol, interface, design]
created: 2026-07-13
status: draft
---

> **TL;DR** Revive and flesh out the `Component` Protocol from `model/common/src/icon4py/model/common/components/components.py` into a usable, well-documented interface for model building blocks.

> **Current direction (2026-07-29):** the design has moved to a **directed-graph composition layer above the `Component`** (chaining, looping, branching, I/O as a sink, conversions as components). The primitives are defined once and are stable across a D0 (today) -> D1 (no-IR eDSL) -> D2 (introspectable steps, opt-in export) -> D3 (serializable IR plus a second interpreter) layering; D3 is a non-breaking addition, not a fork. See the v3 spec in the appendices. NOT FROZEN.

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

- [[personal/msimberg/revive-components/revive-components_spec_v3|SPEC v3 (composition layer)]] - current proposal: a directed-graph composition layer above the `Component`, with a D0->D1->D2->D3 layering and concrete worked examples for the standalone driver, physics driver, dycore sub-stepping, and tracer advection. **NOT FROZEN.**
- [[personal/msimberg/revive-components/revive-components_spec|SPEC v2 (superseded)]] - earlier per-component frozen input/output dataclasses proposal. Superseded by v3; kept as history.
