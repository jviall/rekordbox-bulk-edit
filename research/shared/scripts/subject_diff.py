"""Diff two subject snapshots and print what changed across all three layers.

    uv run python research/shared/scripts/subject_diff.py <content_id> <stageA> <stageB>

Reports DjmdContent column changes, cue-row changes, and per ANLZ file which
tags changed bytes (by SHA-1), plus PPTH and beat-grid moves. Use it after each
convert and re-analyze to see exactly what the step touched.
"""

import json
import sys
from pathlib import Path

if len(sys.argv) < 4:
    raise SystemExit("usage: subject_diff.py <content_id> <stageA> <stageB>")

cid, stage_a, stage_b = sys.argv[1], sys.argv[2], sys.argv[3]
ev = Path(__file__).resolve().parent.parent / "evidence"


def load(stage):
    p = ev / f"subject-{cid}-{stage}.json"
    if not p.exists():
        raise SystemExit(f"missing snapshot: {p.name}")
    return json.loads(p.read_text(encoding="utf-8"))


a, b = load(stage_a), load(stage_b)
print(f"# Diff content {cid}: {stage_a} -> {stage_b}\n")

# ── Content row ───────────────────────────────────────────────────────────
print("## DjmdContent columns")
changed = [(k, a["content"].get(k), b["content"].get(k))
           for k in b["content"] if a["content"].get(k) != b["content"].get(k)]
if changed:
    for k, o, n in changed:
        print(f"  {k}: {o!r} -> {n!r}")
else:
    print("  (no change)")

# ── Cues ──────────────────────────────────────────────────────────────────
print("\n## DjmdCue rows")
if len(a["cues"]) != len(b["cues"]):
    print(f"  count {len(a['cues'])} -> {len(b['cues'])}")
key = lambda c: (c.get("Kind"), c.get("InMsec"))
amap = {key(c): c for c in a["cues"]}
bmap = {key(c): c for c in b["cues"]}
gone = [k for k in amap if k not in bmap]
added = [k for k in bmap if k not in amap]
for k in gone:
    print(f"  removed: Kind={k[0]} InMsec={k[1]}")
for k in added:
    print(f"  added:   Kind={k[0]} InMsec={k[1]}")
for k in amap.keys() & bmap.keys():
    for col in bmap[k]:
        if amap[k].get(col) != bmap[k].get(col):
            print(f"  Kind={k[0]} InMsec={k[1]} {col}: "
                  f"{amap[k].get(col)!r} -> {bmap[k].get(col)!r}")
if len(a["cues"]) == len(b["cues"]) and not gone and not added and \
        all(amap[k] == bmap[k] for k in amap.keys() & bmap.keys()):
    print("  (no change)")

# ── ANLZ ──────────────────────────────────────────────────────────────────
print("\n## ANLZ files")
kinds = set(a["anlz"]) | set(b["anlz"])
any_anlz_change = False
for kind in sorted(kinds):
    ea, eb = a["anlz"].get(kind), b["anlz"].get(kind)
    if ea is None or eb is None:
        print(f"  {kind}: present in only one stage ({'A' if ea else 'B'})")
        any_anlz_change = True
        continue
    lines = []
    if ea["ppth"] != eb["ppth"]:
        lines.append(f"    PPTH: {ea['ppth']!r} -> {eb['ppth']!r}")
    # tag bytes by (type, offset)
    ta = {(t["type"], t["offset"]): t["sha1"] for t in ea["tags"]}
    tb = {(t["type"], t["offset"]): t["sha1"] for t in eb["tags"]}
    # compare by type, allowing offset shifts
    types = {t["type"] for t in ea["tags"]} | {t["type"] for t in eb["tags"]}
    for ty in sorted(types):
        sa = [t["sha1"] for t in ea["tags"] if t["type"] == ty]
        sb = [t["sha1"] for t in eb["tags"] if t["type"] == ty]
        if sa != sb:
            lines.append(f"    {ty}: bytes changed {sa} -> {sb}")
    if ea.get("pqtz") != eb.get("pqtz"):
        lines.append(f"    PQTZ summary: {ea.get('pqtz')} -> {eb.get('pqtz')}")
    if lines:
        any_anlz_change = True
        print(f"  {kind} ({eb['path_tail']}):")
        print("\n".join(lines))
if not any_anlz_change:
    print("  (no change in any ANLZ file)")
