"""Discover what authors a PVB2 tag (read-only correlation).

PVB2 appears only in .EXT ANLZ files, so the relevant universe is tracks that
carry an .EXT (a full analysis). Among those, some have PVB2 and some do not.
This cross-tabulates PVB2 presence against DjmdContent attributes to find what
separates the two groups, which is a lead on what process wrote the tag.

    uv run python research/convert-reanalysis-impact/scripts/pvb2_origin.py

Read-only; close rekordbox first so the read sees committed state.
"""

import struct
from collections import defaultdict

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

db = Rekordbox6Database()


def ext_pvb2_len(path):
    """Return the PVB2 tag length in an .EXT file, or None if absent."""
    with open(path, "rb") as fh:
        data = fh.read()
    len_header = struct.unpack(">I", data[4:8])[0]
    len_file = struct.unpack(">I", data[8:12])[0]
    i = len_header
    found = None
    while i + 12 <= len_file:
        ttype = data[i:i + 4].decode("ascii", "replace")
        lt = struct.unpack(">I", data[i + 8:i + 12])[0]
        if ttype == "PVB2":
            found = lt
        if lt <= 0:
            break
        i += lt
    return found


cols = [c.name for c in tables.DjmdContent.__table__.columns]
date_cols = [c for c in cols if any(
    k in c.lower() for k in ("created", "stock", "release", "date"))]

records = []
contents = db.get_content().all()
for c in contents:
    try:
        paths = db.get_anlz_paths(c.ID)
    except Exception:
        continue
    ext = paths.get("EXT")
    if not ext:
        continue
    try:
        plen = ext_pvb2_len(ext)
    except Exception:
        continue
    records.append({"c": c, "pvb2": plen is not None, "pvb2_len": plen})

db.close()

total = len(records)
with_pvb2 = sum(1 for r in records if r["pvb2"])
print(f"date-like columns available: {date_cols}")
print(f"\ntracks with an .EXT (full-analysis universe): {total}")
print(f"  of those, with PVB2:    {with_pvb2}")
print(f"  of those, without PVB2: {total - with_pvb2}")
if total:
    print(f"  overall PVB2 rate: {100 * with_pvb2 / total:.1f}%")


def contingency(label, keyfn, max_card=40):
    grp = defaultdict(lambda: [0, 0])  # value -> [with_pvb2, without]
    for r in records:
        try:
            v = keyfn(r)
        except Exception:
            v = "<err>"
        grp[v][0 if r["pvb2"] else 1] += 1
    print(f"\n== {label} ==  value: PVB2 / no-PVB2 / %PVB2")
    items = sorted(grp.items(), key=lambda kv: str(kv[0]))
    if len(items) > max_card:
        print(f"  ({len(items)} distinct values; showing all)")
    for v, (yes, no) in items:
        tot = yes + no
        print(f"  {v!r}: {yes} / {no} / {100 * yes / tot:.0f}%")


for attr in ("FileType", "Analysed", "AnalysisUpdated", "SampleRate",
             "BitDepth", "BitRate"):
    contingency(attr, lambda r, a=attr: getattr(r["c"], a))

for dc in date_cols:
    contingency(f"{dc} (year)", lambda r, d=dc: str(getattr(r["c"], d))[:4])

# PVB2 length is expected to scale with duration, not origin; show for context.
lens = sorted({r["pvb2_len"] for r in records if r["pvb2"]})
print(f"\ndistinct PVB2 lengths seen: {lens[:20]}{' ...' if len(lens) > 20 else ''}")
