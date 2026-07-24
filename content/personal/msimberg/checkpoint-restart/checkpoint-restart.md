---
title: Checkpoint/restart — Cycle 37 status overview
author: msimberg
tags: [checkpoint, restart, io, state, serialization, netcdf, dycore, distributed]
created: 2026-07-24
status: draft
---

High-level fact base for checkpoint/restart in ICON4Py, assembled from the Cycle 37 shaping doc, the current `main` codebase, and the `ibm_02` branch prototype. No decisions — just scope, existing pieces, options, and rabbit holes.

See also:
- [[personal/msimberg/revive-components/revive-components|Revive components]] — broader model-state and component-protocol design that a restart mechanism would have to serialize.
- [[personal/msimberg/cleanup-distributed-computation|Cleanup the decomposition directory]] — distributed-computation infrastructure that a production restart would need to interact with.

---

## 1. Scoping from the shaping doc

- **Problem:** ICON4Py has no checkpoint/restart capability.
- **Appetite:** 2 weeks, because current runs are small enough to finish in 24 h.
- **Suggested path:** Evaluate the `ibm_02` branch’s serial 2-checkpoint restart and either port it or design a replacement.
- **Open questions left by the doc:**
  - Add distributed restart now, or stay serial?
  - Reuse `driver_io` or build a dedicated restart module?
  - Are there external libraries worth using instead of a custom solution?

---

## 2. What already exists on `main`

### Read-only restart for initialization

`model/common/src/icon4py/model/common/initial_condition/from_file.py` already has a *restart-from-serialbox-data* path:

- `FromFileConfig.is_restart`
- `read_restart_from_file(...)` loads `rho`, `exner`, `theta_v`, `vn`, `w`, `exner_pr`, and predictor/corrector advective tendencies from serialized ICON savepoints.
- It does **not** support tracers (`NotImplementedError`).
- It is used when `start_of_timestepping != start_of_simulation`.

### Output / IO infrastructure

`model/common/src/icon4py/model/common/io/io.py`:

- `IOConfig`, `IOMonitor`, `FieldGroupMonitor` for NetCDF output.
- `NETCDFWriter` supports parallel NetCDF4 (when MPI is available) and appending time slices.
- Contains an explicit TODO: *“take care of this when implementing restart”* regarding output-file overwrite protection.

### Driver / time-loop state

- `model/driver/src/icon4py/model/driver/icon4py_driver.py`: `TimeLoop` already has `restart_mode` and `_is_first_step_in_simulation`.
- `model/standalone_driver/src/icon4py/model/standalone_driver/driver_states.py`: `ModelTimeVariables` tracks `start_of_simulation`, `start_of_timestepping`, elapsed time, substeps, CFL-watch mode, etc.

So `main` can *read* a serialbox-style restart for initialization, and has an output stack, but has no *write* side for periodic checkpoints.

---

## 3. What the `ibm_02` branch implemented

The branch added a small, self-contained, **serial** checkpoint writer/reader.

### Location and mechanism

- File: `model/common/src/icon4py/model/common/io/restart.py`
- Class: `RestartManager`
- Format: Python `pickle` containing NumPy arrays.
- Two-checkpoint scheme: alternating `restart_0.pkl` / `restart_1.pkl`, plus `.meta` sidecars, using temp-file-then-rename for atomicity.
- Configured via environment variables:
  - `ICON4PY_RESTART_FREQUENCY` (default 10 000 steps)
  - `ICON4PY_OUTPUT_DIR/restart`

### Driver integration

In `icon4py_driver.py`:

- At the start of `TimeLoop.time_integration`, call `restore_from_restart(...)`.
- If a checkpoint is found, set the loop start to `time_step_number + 1`, mark `_is_first_step_in_simulation = False`, and advance the simulation date by that many steps.
- After each step, if `(time_step + 1) % RESTART_FREQUENCY == 0`, call `write_restart(...)`.

### Saved state

- Prognostic state for both `.current` and `.next`: `vn`, `w`, `rho`, `exner`, `theta_v`.
- Diagnostic state for `solve_nonhydro`:
  - `perturbed_exner_at_cells_on_model_levels`
  - `vertical_wind_advective_tendency.predictor`
  - `vertical_wind_advective_tendency.corrector`
- Metadata: `time_step_number`, `restart_timestamp`.

Fields are stored as `{"data": field.asnumpy(), "dims": [...]}` and reconstructed with `gtx.as_field(..., allocator=backend)`.

### Gaps in `ibm_02`

- No tracers.
- No diffusion diagnostic state, no advection prep state.
- No actual datetime / elapsed-time metadata; date is recomputed from step count × dtime.
- No adaptive-substep state (`ndyn_substeps_var`, CFL-watch mode).
- No random seeds or stochastic-physics state.
- No config provenance.
- No MPI / distributed support; serial only, no file locking.
- No output-file continuity handling.
- Bound to the same backend used at write time.

---

## 4. State inventory: what a full restart might need

| Category | Examples |
|---|---|
| **Prognostic** | `rho`, `exner`, `theta_v`, `vn`, `w`, tracers |
| **Dycore diagnostics carried across steps** | `exner_pr`, `ddt_vn_apc_pc`, `ddt_w_adv_pc` |
| **Other component state** | diffusion diagnostics, advection prep fields |
| **Time/integration metadata** | current date, `start_of_simulation`, `start_of_timestepping`, remaining steps, elapsed time, `is_first_step_in_simulation`, `ndyn_substeps_var`, CFL-watch mode |
| **Random state** | seeds for stochastic physics |
| **Provenance** | grid, physics, dtime, precision |
| **Decomposition** | rank count, owner masks, domain decomposition (for distributed restart) |
| **Output continuity** | current output files, step/file counters |

Usually **not** saved: static fields (metrics, interpolation coefficients), compiled GT4Py stencils.

---

## 5. Format and technology options

| Approach | Notes |
|---|---|
| **NetCDF4 (existing `NETCDFWriter`)** | Already used for output; supports parallel I/O; CF metadata friendly. |
| **Serialbox (existing test format)** | Used for reading Fortran ICON state; not ideal for production checkpoint writing. |
| **HDF5 / PnetCDF** | Standard parallel I/O; more chunking/compression control. |
| **Zarr** | Cloud/storage-friendly chunked format; good for parallel writes. |
| **Custom binary per rank** | Fast and simple, but fragile and not portable. |
| **Checkpointing libraries** | e.g. VeloC, FTI, DMTCP. The doc notes nothing useful was found; would need re-verification. |
| **General serialization** | `torch.save`, `cloudpickle`, `numpy` `.npz`. Convenient for prototypes, risky for long-term reproducibility. |

`ibm_02` chose `pickle`; `main`’s diagnostic output already chose NetCDF4.

---

## 6. Key design tradeoffs

- **Exact restart vs. scientific restart**
  - *Exact* requires every time-dependent quantity (tendencies, previous-step fields, random seeds).
  - *Scientific* may only need prognostics + date; simpler but not bit-reproducible.

- **Serial vs. distributed**
  - Serial is what `ibm_02` did; simple but does not scale.
  - Distributed needs per-rank files or parallel NetCDF; necessary for production.

- **Write frequency**
  - Every N steps, every N hours, fixed simulation times, wall-clock timer, or user signal.
  - More frequent = more I/O and disk; less frequent = more lost work.

- **Synchronous vs. asynchronous**
  - Synchronous pauses the time loop; simplest.
  - Asynchronous copies state and writes in background; faster but more memory and complexity.

- **Rolling checkpoints**
  - `ibm_02` uses two alternating files to avoid overwriting the only good checkpoint during I/O.
  - More than two can be useful for longer runs.

- **Portability**
  - Can a checkpoint from N ranks restart on M ranks? Usually not without extra remapping.
  - For a 2-week scope, same-rank/same-decomposition is the realistic assumption.

---

## 7. Rabbit holes

- **GT4Py field backends:** fields may be on GPU; any write path must synchronize and copy to host memory.
- **Field reconstruction:** reading back into `gtx.Field` objects requires correct dimensions, origins, and allocator.
- **Halo consistency:** after a distributed restore, halos may need an exchange before neighbor stencils are valid.
- **Tracer restart:** current code excludes tracers because tracer data lives in a different savepoint.
- **Adaptive substeps / CFL watch mode:** these can change at runtime and must be persisted.
- **Output file continuity:** existing output monitor refuses to overwrite; restart must append or start new files cleanly.
- **Mixed precision:** decide storage precision vs. working precision.
- **Bit reproducibility:** verifying restart correctness requires dedicated regression tests.
- **Disk usage:** full 3D state + tracers is large; compression and selective checkpointing may matter.
- **Configuration coupling:** restart files need enough provenance to detect mismatched grid/physics/dtime.
- **Fortran ICON interoperability:** reading Fortran-written restarts (or vice versa) requires format/naming alignment.

---

## 8. Plausible scope levels, given the 2-week appetite

### A. Port `ibm_02` as-is
- Move `RestartManager` to `main`.
- Replace environment variables with a proper config object.
- Keep pickle and serial-only behavior.
- Quick, but inherits all `ibm_02` gaps.

### B. Port `ibm_02` but switch to NetCDF
- Use the existing `NETCDFWriter` / `FieldGroupMonitor` machinery.
- Adds metadata, compression, and a more maintainable format.
- Still serial; still limited saved state.

### C. Extend the saved state
- Add tracers, diffusion diagnostics, advection prep, actual datetime, elapsed time, substeps, CFL mode.
- May still be serial and use either pickle or NetCDF.
- Gets closer to a real restart, but expands testing surface.

### D. Distributed restart
- Per-rank files or parallel NetCDF, halo exchange on restore, rank-coordinated metadata.
- Likely exceeds the 2-week appetite unless it is the only goal.

---

## Bottom line

The `ibm_02` branch demonstrates that a serial dycore-only checkpoint can be integrated into `TimeLoop` with modest changes. The current `main` already has a read-only serialbox restart path and a NetCDF output stack. The central design decision is therefore not *whether* checkpoint/restart is feasible, but how much of `ibm_02`’s simplicity to keep, how much to replace with the existing `io` infrastructure, and whether to stay within the 2-week serial scope or expand toward distributed I/O.
