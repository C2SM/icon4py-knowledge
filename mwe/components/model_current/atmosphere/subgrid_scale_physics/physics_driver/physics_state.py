from typing import Final

import gt4py.next as gtx

from model_current.common.states import diagnostic_state, model, prognostic_state as prognostics, tracer_states
import ops

MOISTURE_SPECIES: Final = ("qv",)


class EntryState:
    def __init__(self) -> None:
        self.diagnostics = diagnostic_state.initialize_diagnostic_state()
        self.exner: ops.Field
        self.theta_v: ops.Field
        self.vn: ops.Field
        self.tracers: tracer_states.TracerState

    def diagnose_from(self, prognostic: prognostics.PrognosticState, tracers: tracer_states.TracerState) -> None:
        self.exner = prognostic.exner
        self.theta_v = prognostic.theta_v
        self.vn = prognostic.vn
        self.tracers = tracers
        ops.compute_temperature(prognostic.theta_v, prognostic.exner, self.diagnostics.temperature)
        ops.edge_2_cell_vector_rbf_interpolation(prognostic.vn, self.diagnostics.u)


class TendencyAccumulators:
    def __init__(self) -> None:
        self.acc: dict[str, ops.Field] = {}

    def zero(self) -> None:
        for buffer in self.acc.values():
            ops.arr(buffer)[...] = 0.0

    def accumulate(self, outputs: dict[str, ops.Field], outputs_properties: dict[str, model.FieldMetaData]) -> None:
        for name, props in outputs_properties.items():
            if props.kind != model.FieldKind.TENDENCY:
                continue
            field = outputs[name]
            if (buffer := self.acc.get(name)) is None:
                buffer = self.acc[name] = gtx.zeros(field.domain, dtype=field.dtype)
            ops.arr(buffer)[...] += ops.arr(field)


class ApplyToPrognostic:
    def __init__(self) -> None:
        self._new_te = ops.field(ops.CELL_K)
        self._ddt_vn = ops.field(ops.EDGE_K)

    def __call__(self, entry_state: EntryState, accumulators: TendencyAccumulators, dt_seconds: float) -> None:
        acc = accumulators.acc
        tracers = entry_state.tracers
        for name in MOISTURE_SPECIES:
            key = f"tend_{name}"
            if key in acc:
                tracer = getattr(tracers, name)
                ops.arr(tracer)[...] += dt_seconds * ops.arr(acc[key])
        if "tend_temperature" in acc:
            ops.arr(self._new_te)[...] = ops.arr(entry_state.diagnostics.temperature) + dt_seconds * ops.arr(
                acc["tend_temperature"]
            )
            ops.update_exner_and_theta_v(
                self._new_te, entry_state.exner, entry_state.theta_v, entry_state.exner, entry_state.theta_v
            )
        if "tend_u" in acc:
            ops.compute_vn_from_uv(acc["tend_u"], self._ddt_vn)
            ops.arr(entry_state.vn)[...] += dt_seconds * ops.arr(self._ddt_vn)


class DiagnosticsStore:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, ops.Field]] = {}

    def allocate(self, process_name: str, outputs_properties: dict[str, model.FieldMetaData]) -> dict[str, ops.Field]:
        buffers: dict[str, ops.Field] = {}
        for name, props in outputs_properties.items():
            if props.kind == model.FieldKind.TENDENCY:
                continue
            assert props.dims is not None
            buffers[name] = ops.field(tuple(props.dims))
        self._store[process_name] = buffers
        return buffers

    def __getitem__(self, process_name: str) -> dict[str, ops.Field]:
        return self._store[process_name]
