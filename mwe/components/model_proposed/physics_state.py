from model_proposed.common import framework as fw, quantities as qty


# What the physics driver offers its processes each step: the prognostics it
# received plus the diagnostics it derived from them. Each process picks its
# Input from here by hand (`collect_input` next to the process), as
# `as_component_input` does in icon4py.
class EntryState(fw.State):
    vn: qty.Vn.EdgeK
    exner: qty.Exner.CellK
    theta_v: qty.ThetaV.CellK
    qv: qty.Qv.CellK
    temperature: qty.Temperature.CellK
    u: qty.U.CellK
