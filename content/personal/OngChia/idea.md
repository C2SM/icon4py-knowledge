---
title: Scientific Test Cases for icon4py
author: OngChia
tags: [testing, test-cases, scientific-validation, dycore, physics, benchmarking]
created: 2026-07-27
status: draft
---

> **TL;DR** Propose a prioritized set of scientific test cases — from idealized dynamical-core benchmarks to full-physics simulations — to verify correctness and characterize the numerical properties of icon4py ahead of its first uncoupled simulation milestone.

## Problem / motivation

The icon4py driver has been progressing steadily, with configuration and I/O both under active development. Now is the right time to decide which simulation test cases to create in order to scientifically validate the model.

## Proposal

I propose two categories of test cases: those without a reference solution, used to understand the numerical properties of the model, and those with an analytic or laboratory reference solution, used to verify correctness and accuracy.

### Without reference solution

These test cases probe the qualitative numerical behavior of the model. Listed in approximate order of implementation complexity:

1. **Dynamical core:** Jablonowski–Williamson baroclinic wave. Reference: [Jablonowski and Williamson 2007](https://rmets.onlinelibrary.wiley.com/doi/abs/10.1256/qj.06.12)
2. **Dynamical core:** 3D mountain waves.
3. **Dynamical core:** [Held–Suarez setup](https://journals.ametsoc.org/view/journals/bams/75/10/1520-0477_1994_075_1825_apftio_2_0_co_2.xml)
4. **Dynamical core + Microphysics + Turbulence:** Weisman–Klemp warm bubble. As has been done in ICON, this test can also be used to check whether mass and energy conservation is correctly satisfied with basic physics parameterizations and without any energy or mass input from the boundary. It also allows a qualitative assessment of the model's ability to reproduce supercell growth. Reference: [Weisman and Klemp 1982](https://journals.ametsoc.org/view/journals/mwre/110/6/1520-0493_1982_110_0504_tdonsc_2_0_co_2.xml)
5. **Dynamical core + Microphysics + Turbulence + Radiation:** Radiative–convective equilibrium and self-aggregation of convection. Reference: [Muller and Held 2012](https://journals.ametsoc.org/view/journals/atsc/69/8/jas-d-11-0257.1.xml)
6. **Dynamical core + Microphysics + Turbulence + Radiation:** Aqua-planet simulation.

### With analytic or laboratory reference solution

These test cases verify correctness and measure numerical accuracy:

1. **Dynamical core:** Jablonowski–Williamson steady-state (static) flow. We can assess convergence by examining how the deviation from the initial condition changes with grid resolution. Reference: [Jablonowski and Williamson 2007](https://rmets.onlinelibrary.wiley.com/doi/abs/10.1256/qj.06.12)
2. **Advection:** Convergence tests for horizontal and vertical advection (reviving PRs by David Strasser: [#PR580](https://github.com/C2SM/icon4py/pull/580), [#PR597](https://github.com/C2SM/icon4py/pull/597), [#PR625](https://github.com/C2SM/icon4py/pull/625))
3. **Advection:** Transport of a scalar field on a sphere. Reference: [Nair and Lauritzen 2010](https://www.sciencedirect.com/science/article/pii/S0021999110004511). This test compares the final transported field against the initial condition to assess the accuracy of the advection scheme.
4. **Dynamical core + Advection:** 2D gravity waves over idealized topography. Reference: [Schär et al. 2002](https://journals.ametsoc.org/view/journals/mwre/130/10/1520-0493_2002_130_2459_antfvc_2.0.co_2.xml)
5. **Dynamical core + Turbulence:** Two possible test cases: (a) following [Taylor and Green 1937](https://royalsocietypublishing.org/rspa/article/158/895/499/5572/Mechanism-of-the-production-of-small-eddies-from), a 3D periodic domain initialized with vortices whose numerical solution can be compared against the analytical solution over a short integration; and (b) dry convective PBL flow from Clark et al. (1971), for which details can be found in [Moeng 1984](https://journals.ametsoc.org/view/journals/atsc/41/13/1520-0469_1984_041_2052_alesmf_2_0_co_2.xml?tab_body=pdf).
6. **Dynamical core + Advection + Microphysics + Turbulence:** Growth of a non-precipitating convective boundary layer compared against an approximate analytical growth-rate solution. References: [Stevens 2007](https://journals.ametsoc.org/view/journals/atsc/64/8/jas3983.1.xml); [Dipankar et al. 2015](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1002/2015MS000431) (more complex experiments).

## Plan

Not all of the tests listed above are equally urgent before the end-of-2026 milestone set for the EXCLAIM project's first uncoupled simulation. The Jablonowski–Williamson and mountain-wave test cases are already available and provide a natural starting point: they can immediately yield plots that qualitatively demonstrate the model's intrinsic properties, as well as quantitative metrics that check the correctness and accuracy of the underlying algorithms. In parallel, the advection convergence tests created by David Strasser could be revived.

The guiding criterion for prioritization should be whether a test provides a useful first step by covering both qualitative and quantitative evaluation of the model components that are critical to the uncoupled simulation. With that in mind, I suggest the following implementation order:

1. JW baroclinic wave and static-flow tests
2. Mountain-wave tests (Schär and Gaussian-mountain configurations)
3. Advection convergence tests (including the scalar-advection-on-a-sphere test)
4. Turbulence test cases
5. Weisman–Klemp simulation
6. RCE or aqua-planet simulation

The remaining test cases can be added in the future.
