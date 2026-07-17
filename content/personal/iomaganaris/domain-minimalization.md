---
title: Verify that the domains of all the GT4Py programs are as minimal as possible using an LLM
author: iomaganaris
tags: [dycore, diffusion, tracer_advection, autoresearch]
created: 2026-07-17
status: draft
---

> **TL;DR** Let an LLM check the whole `icon4py` frontend code to figure out if there are opportunities to restrict the domain of GT4Py field operators/programs

## Problem / motivation

In [icon4py PR#1378](https://github.com/C2SM/icon4py/pull/1378) Jacopo figured out that by restricting the domain computation of field it fixed not only the correctness but it also helped the `GT4Py-DaCe` passes to split and fuse more beneficially the Maps/GPU kernels.
We are wondering if there are more cases like that in `icon4py`.

## Proposal

The idea is to feed the `icon4py` frontend code for `dycore`, `diffusion` and `tracer_advection` to an LLM and explain to it or let it figure out the concepts of computation domains in the frontend. Then we can ask it to figure out if there are domains in `GT4Py programs` of `icon4py` that can be restricted without any influence at the generated results. For that purpose we have to give it a good test to check its changes with. Doing this in a completely agentic mode is useful because compiling all the `GT4Py` programs is time consuming.

## Alternatives considered

Go program by program by hand I guess.

## Open questions / conflicts

How can the domain restriction be done with the help of the `GT4Py domain inference`. My guess is that the necessary information to make the `GT4Py domain inference` as good as possible are missing from the frontend code and that's why we ended up in the case of PR#1378.
