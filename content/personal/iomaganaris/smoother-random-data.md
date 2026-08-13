---
title: Use smoother random data in the StencilTests to lower the relative tolerance
author: iomaganaris
tags: [testing, stencil-tests, random-data, numerical-precision, tolerances]
created: 2026-06-11
status: draft
---

> **TL;DR** `StencilTest` inputs are independent uniform random values. For
> derivative-like operators that creates artificial, grid-scale jumps and can
> magnify backend-specific floating-point roundoff. Add a deterministic smooth
> field generator to the test allocator, use it for derivative-sensitive inputs,
> and demonstrate that the shared relative tolerance can return to `1e-7`.

## Problem / motivation

`StencilTest.verify_data()` compares every output with one global relative
tolerance. A TODO in `model/testing/stencil_tests.py`, introduced for PR #861,
records that the tolerance was relaxed from `1e-7` to cover CI-only floating
point discrepancies. The linked failing pipeline attributes the likely cause to
derivatives of random input data.

The current `DataAllocationWrapper.random_field()` delegates to
`data_allocation.random_field()`, producing independent values uniformly drawn
from `[low, high)`. Such a field deliberately contains discontinuities at every
cell or edge. Difference, gradient, divergence, interpolation, and reduction
stencils therefore operate on much larger local variations than realistic model
fields. Differences in operation ordering, fused multiply-add, and GPU versus
CPU reduction order are then more visible against the NumPy reference.

The relaxed tolerance applies to all stencil tests, including simple operators
for which it masks useful regressions. The goal is not to make the reference and
compiled implementation agree by construction; it is to use physically
plausible, reproducible inputs for the tests whose purpose is functional
verification.

## Proposal

Add `smooth_field()` to `DataAllocationWrapper`, with the same dimensions,
dtype, `extend`, and allocator behaviour as `random_field()`. It should create
the values on the host and use the existing allocation path to place the field
on the selected backend device.

For each structured dimension, construct a normalized coordinate in `[0, 1]`.
Build a bounded value from a small fixed set of low-frequency basis functions,
for example a constant plus products of sine and cosine modes with frequencies
one to three. Use a fixed seed only for the coefficients or phases, rather than
sampling independently at every field location. Map the result to the requested
`[low, high)` interval and preserve the requested floating-point dtype.

For unstructured horizontal dimensions, use mesh connectivity rather than the
storage index as the notion of locality. A practical first implementation is to
start from a deterministic seeded field and apply several rounds of neighbor
averaging with the grid connectivity, retaining a non-zero contribution from
the original field. This supports the same test grids and produces bounded
variation across connected cells, edges, or vertices. Vertical dimensions can
use the structured-coordinate construction.

The initial migration should be selective:

1. Identify tests that feed a field into a derivative, divergence, gradient,
	 flux difference, or repeated neighbor interpolation.
2. Replace only those continuous physical inputs with `smooth_field()`.
	 Keep `random_field()` for pointwise algebra, thresholding, and tests intended
	 to exercise irregular data; keep `random_mask()` and `random_sign()` for
	 discrete control inputs.
3. Run the affected suites repeatedly on the CI backend matrix with
	 `rtol=1e-7`, including the pipeline configuration that failed in PR #861.
4. If the suites remain stable, restore the shared `_RELATIVE_TOLERANCE` to
	 `1e-7`. If individual operations still need looser bounds, give them an
	 explicit, documented tolerance rather than retaining a looser global default.

The discriminating check is straightforward: with unchanged implementations and
references, the same derivative-sensitive suites should fail intermittently
with independent random fields at `1e-7` but pass repeatedly with smooth fields
at that tolerance. A reproducible failure must be retained as a regression case
before changing the global tolerance.

## Alternatives considered

**Keep `rtol=3e-6`.** This is operationally simple but weakens every stencil
test, including operations unaffected by the original numerical issue.

**Set per-test or per-output tolerances only.** This is appropriate for known
ill-conditioned operations, but treating all affected tests this way leaves the
unrealistic input distribution unchanged and scatters numerical policy through
the suite.

**Use recorded ICON/Serialbox fields.** These are more realistic and valuable
for integration validation, but add I/O, fixtures, and test-data maintenance to
the fast generated-input tests. They complement rather than replace smooth
generated fields.

**Use only analytic fields.** A single linear or trigonometric field gives an
excellent oracle for a particular operator, but it is too regular to exercise
the range of combinations currently covered by generated data. A small,
deterministic mixture of low-frequency modes retains variation while bounding
derivatives.

## Open questions / conflicts

This overlaps with [[personal/havogt/declarative-testing-harness/declarative-testing-harness|Declarative testing harness]], which proposes explicit per-output tolerance
policy and notes the same global `rtol=3e-6`. The proposals are complementary:
that work governs reporting and tolerance ownership, while this one improves
the generated inputs that determine the numerical stress placed on the test.

Questions to settle in a proof of concept:

- Which connectivities should define smoothing for each unstructured location
	dimension, and how should boundary or missing neighbors be treated?
- How many smoothing rounds and which retained-noise fraction give a useful
	balance between stable derivatives and non-trivial test coverage?
- Should `smooth_field()` be the default for floating-point `random_field()`,
	or remain opt-in until stencil suites have been audited?
- Which CI backend and precision combinations failed in PR #861, and can one be
	made deterministic enough to serve as the regression check?

## Appendices

Relevant implementation surface at the time of writing:

- `model/testing/src/icon4py/model/testing/stencil_tests.py` defines
	`DataAllocationWrapper.random_field()` and the shared relative tolerance used
	by `StencilTest.verify_data()`.
- The PR #861 TODO links the original CI failure:
	<https://gitlab.com/cscs-ci/ci-testing/webhook-ci/mirrors/5125340235196978/2255149825504673/-/pipelines/2184694383>.
