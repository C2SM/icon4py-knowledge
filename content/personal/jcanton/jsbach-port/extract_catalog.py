#!/usr/bin/env python3
"""Extract the jsbach field catalog from *_memory_class.f90 Add_var calls.

Produces field_catalog.csv: one row per model variable with
  process, name, dim (2D/3D), vgrid, state (prognostic/diagnostic/conditional),
  output, output_level, units, long-name.

Run from anywhere; edit SRC if the tree moves.
"""
import os, re, glob, csv, collections

SRC = os.environ.get("JSBACH_SRC",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

SURFACE_VGRIDS = {"surface", "vgrid_2d"}  # -> 2D (no vertical); everything else -> 3D

def join_continuations(text):
    out, buf = [], ""
    for line in text.splitlines():
        s = line.rstrip()
        if s.endswith("&"):
            buf += s[:-1] + " "
        else:
            buf += s; out.append(buf); buf = ""
    if buf:
        out.append(buf)
    return out

call_re     = re.compile(r"Add_var\s*\((.*)", re.IGNORECASE)
str_re      = re.compile(r"'([^']*)'")
hgrid_re    = re.compile(r"\bhgrid\s*,\s*([A-Za-z_]\w*)", re.IGNORECASE)
tcf_re      = re.compile(r"t_cf\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'", re.IGNORECASE)
lrestart_re = re.compile(r"lrestart\s*=\s*([^\s,)]+)", re.IGNORECASE)
loutput_re  = re.compile(r"loutput\s*=\s*([^\s,)]+)", re.IGNORECASE)
outlvl_re   = re.compile(r"output_level\s*=\s*([^\s,)]+)", re.IGNORECASE)

rows = []
files = sorted(glob.glob(os.path.join(SRC, "**", "*_memory_class.f90"), recursive=True))
for f in files:
    proc = os.path.basename(os.path.dirname(f))
    with open(f, encoding="utf-8", errors="replace") as fh:
        logical = join_continuations(fh.read())
    for ln in logical:
        m = call_re.search(ln)
        if not m:
            continue
        body = m.group(1)
        sm = str_re.search(body)
        if not sm:
            continue
        name = sm.group(1)
        hg = hgrid_re.search(body)
        vgrid = hg.group(1).lower() if hg else "?"
        dim = "2D" if vgrid in SURFACE_VGRIDS else ("3D" if vgrid != "?" else "?")
        tcf = tcf_re.search(body)
        units = tcf.group(2) if tcf else ""
        longname = tcf.group(3) if tcf else ""
        lr = lrestart_re.search(body)
        if lr:
            v = lr.group(1).lower()
            state = ("prognostic" if (".true." in v or "local" in v or v.endswith("_loc"))
                     else "diagnostic" if ".false." in v else "conditional")
        else:
            state = "diagnostic"
        lo = loutput_re.search(body)
        out = "no" if (lo and ".false." in lo.group(1).lower()) else "yes"
        outlvl = outlvl_re.search(body)
        rows.append(dict(process=proc, name=name, dim=dim, vgrid=vgrid, state=state,
                         output=out, output_level=outlvl.group(1) if outlvl else "",
                         units=units, long=longname, file=os.path.basename(f)))

out_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "field_catalog.csv")
with open(out_csv, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["process","name","dim","vgrid","state",
                                       "output","output_level","units","long","file"])
    w.writeheader(); w.writerows(rows)

print(f"TOTAL fields: {len(rows)}  from {len(files)} memory_class files")
print("state:", dict(collections.Counter(r["state"] for r in rows)))
print("dim:  ", dict(collections.Counter(r["dim"] for r in rows)))
print("wrote:", out_csv)
