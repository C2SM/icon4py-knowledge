from model_proposed.common import framework as fw, quantities as qty


# What the physics driver derives from the prognostics each step, in buffers
# it owns (the `DiagnosticState` of icon4py's `EntryState`).
class Diagnostics(fw.State):
    temperature: fw.Field[qty.TemperatureOnCellK]
    u: fw.Field[qty.UOnCellK]


# What the physics driver offers its processes each step: the prognostics it
# received plus the diagnostics it derived from them. Each process picks its
# Input from here by hand (`collect_input` next to the process), as
# `as_component_input` does in icon4py.
class EntryState(fw.State):
    vn: fw.Field[qty.VnOnEdgeK]
    exner: fw.Field[qty.ExnerOnCellK]
    theta_v: fw.Field[qty.ThetaVOnCellK]
    qv: fw.Field[qty.QvOnCellK]
    temperature: fw.Field[qty.TemperatureOnCellK]
    u: fw.Field[qty.UOnCellK]
