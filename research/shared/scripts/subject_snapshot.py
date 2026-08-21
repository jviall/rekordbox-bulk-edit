"""Full three-layer snapshot of one track for the convert impact test.

Captures the DjmdContent row, every DjmdCue row, and per ANLZ file a raw tag
walk with a SHA-1 of each tag's bytes plus parsed beat-grid and cue summaries.
Writes evidence/subject-<id>-<stage>.json. Read-only; close rekordbox first so
the read sees committed state.

    uv run python research/shared/scripts/subject_snapshot.py <content_id> <stage>

Stage is a free label, e.g. 00-baseline, 10-postconvert, 20-postanalyze.
The per-tag SHA-1 is the load-bearing field: it proves convert never rewrites
the ANLZ (hashes hold) and that re-analyze does (hashes move). Diff two stages
with subject_diff.py.
"""

import hashlib
import json
import struct
import sys
from datetime import datetime
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from pyrekordbox.anlz import AnlzFile
from pyrekordbox.db6 import tables

if len(sys.argv) < 3:
    raise SystemExit("usage: subject_snapshot.py <content_id> <stage>")

cid, stage = sys.argv[1], sys.argv[2]
out_path = (
    Path(__file__).resolve().parent.parent
    / "evidence"
    / f"subject-{cid}-{stage}.json"
)


def jsafe(v):
    return v if isinstance(v, (int, float, str, type(None))) else str(v)


def raw_walk(path):
    """Return (list of per-tag dicts, PPTH string) for an ANLZ file.

    Each tag dict carries its type, byte offset, header/tag lengths, and a SHA-1
    of the tag's raw bytes so any content change is detectable without parsing.
    """
    data = Path(path).read_bytes()
    len_header = struct.unpack(">I", data[4:8])[0]
    len_file = struct.unpack(">I", data[8:12])[0]
    i = len_header
    tags = []
    ppth = None
    while i + 12 <= len_file:
        ttype = data[i:i + 4].decode("ascii", "replace")
        lh = struct.unpack(">I", data[i + 4:i + 8])[0]
        lt = struct.unpack(">I", data[i + 8:i + 12])[0]
        if lt <= 0:
            tags.append({"type": ttype, "offset": i, "len_header": lh,
                         "len_tag": lt, "sha1": None})
            break
        body = data[i:i + lt]
        tags.append({"type": ttype, "offset": i, "len_header": lh,
                     "len_tag": lt, "sha1": hashlib.sha1(body).hexdigest()})
        if ttype == "PPTH":
            lp = struct.unpack(">I", data[i + 12:i + 16])[0]
            try:
                ppth = data[i + 16:i + 16 + lp - 2].decode("utf-16-be", "replace")
            except Exception:
                ppth = "<err>"
        i += lt
    return tags, ppth


def parse_grid_and_cues(anlz):
    """Human-readable beat-grid and ANLZ cue-list summaries from a parsed file."""
    out = {}
    try:
        pqtz = anlz.get_tag("PQTZ")
        if pqtz.count:
            times = list(pqtz.get_times())
            times_repr = ",".join(f"{t:.4f}" for t in times)
            out["pqtz"] = {
                "beats": int(pqtz.count),
                "bpm_avg": round(float(pqtz.bpms_average), 3),
                "first_s": round(float(times[0]), 4),
                "last_s": round(float(times[-1]), 4),
                "times_sha1": hashlib.sha1(times_repr.encode()).hexdigest(),
                "times": [round(float(t), 4) for t in times],
            }
    except Exception:
        pass
    cuelists = []
    for ttype in ("PCO2", "PCOB"):
        for tag in anlz.getall_tags(ttype):
            try:
                n = len(tag.content.entries)
            except Exception:
                n = None
            kind = getattr(tag.content, "type", getattr(tag.content, "cue_type", None))
            cuelists.append({"tag": ttype, "obj_type": jsafe(kind), "count": n})
    if cuelists:
        out["anlz_cue_lists"] = cuelists
    return out


db = Rekordbox6Database()

content = db.get_content(ID=cid)
row = {col.name: jsafe(getattr(content, col.name)) for col in content.__table__.columns}

cue_rows = (
    db.session.query(tables.DjmdCue)
    .filter_by(ContentID=cid)
    .order_by(tables.DjmdCue.InMsec)
    .all()
)
cues = [
    {col.name: jsafe(getattr(cue, col.name)) for col in cue.__table__.columns}
    for cue in cue_rows
]

paths = db.get_anlz_paths(cid)

anlz = {}
for kind, p in paths.items():
    if not p:
        continue
    tags, ppth = raw_walk(p)
    entry = {
        "path_tail": str(p).split("USBANLZ")[-1],
        "ppth": ppth,
        "tags": tags,
    }
    # Parse is best-effort: pyrekordbox chokes on some ANLZ variants, but the
    # raw tag walk and hashes above stand on their own.
    try:
        entry.update(parse_grid_and_cues(AnlzFile.parse_file(p)))
    except Exception as e:
        entry["parse_error"] = f"{type(e).__name__}: {e}"
    anlz[kind] = entry

db.close()

snapshot = {
    "content_id": cid,
    "stage": stage,
    "captured_at": datetime.now().isoformat(timespec="seconds"),
    "content": row,
    "cues": cues,
    "anlz": anlz,
}

out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

print(f"Snapshot written: {out_path.name}")
print(f"  FileType={row.get('FileType')} SR={row.get('SampleRate')} "
      f"BD={row.get('BitDepth')} BR={row.get('BitRate')} "
      f"FileSize={row.get('FileSize')} Analysed={row.get('Analysed')}")
print(f"  cues={len(cues)}  anlz_files={list(anlz)}")
for kind, e in anlz.items():
    grid = e.get("pqtz", {})
    print(f"  {kind}: ppth={e['ppth']!r} tags={len(e['tags'])} "
          f"grid_beats={grid.get('beats')} first={grid.get('first_s')}s")
