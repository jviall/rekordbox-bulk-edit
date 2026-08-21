"""Diff two export snapshots and print what changed across the drive.

    uv run python research/convert-export-impact/scripts/export_diff.py <stageA> <stageB>

Reports Contents/ file changes (added, removed, bytes changed, mtime-only) with
a per-track extension map that makes replace-vs-orphan-vs-duplicate legible;
per-track USBANLZ changes (PPTH, tag bytes by type, beat grid, and device cue
lists with positions); and which device-DB blobs moved. Use it after each
re-export or sync to see exactly what the step touched.
"""

import json
import sys
from pathlib import Path

if len(sys.argv) < 3:
    raise SystemExit("usage: export_diff.py <stageA> <stageB>")

stage_a, stage_b = sys.argv[1], sys.argv[2]
ev = Path(__file__).resolve().parent.parent / "evidence"


def load(stage):
    p = ev / f"export-{stage}.json"
    if not p.exists():
        raise SystemExit(f"missing snapshot: {p.name}")
    return json.loads(p.read_text(encoding="utf-8"))


def stem_key(rel):
    """(parent dir, filename without extension) — one musical track's identity."""
    p = Path(rel)
    return p.parent.as_posix(), p.stem


a, b = load(stage_a), load(stage_b)
print(f"# Export diff: {stage_a} -> {stage_b}\n")

# ── Contents/ ───────────────────────────────────────────────────────────────
print("## Contents/ audio")
am = {c["rel"]: c for c in a["contents"]}
bm = {c["rel"]: c for c in b["contents"]}
removed = sorted(set(am) - set(bm))
added = sorted(set(bm) - set(am))
common = set(am) & set(bm)
bytes_changed = sorted(r for r in common if am[r]["sha1"] != bm[r]["sha1"])
mtime_only = sorted(r for r in common
                    if am[r]["sha1"] == bm[r]["sha1"] and am[r]["mtime"] != bm[r]["mtime"])

for r in removed:
    print(f"  removed: {r} ({am[r]['size']} bytes)")
for r in added:
    print(f"  added:   {r} ({bm[r]['size']} bytes)")
for r in bytes_changed:
    print(f"  changed: {r} ({am[r]['size']}->{bm[r]['size']} bytes, sha1 differs)")
for r in mtime_only:
    print(f"  touched: {r} (mtime only, bytes identical)")
if not (removed or added or bytes_changed or mtime_only):
    print("  (no change)")

# Per-track extension map for any track whose file set changed: this is what
# separates an in-place replace from an orphaned old file or a duplicate.
changed_stems = {stem_key(r) for r in removed + added}
if changed_stems:
    print("\n  per-track extensions (A -> B):")
    for key in sorted(changed_stems):
        exts_a = sorted(Path(r).suffix for r in am if stem_key(r) == key)
        exts_b = sorted(Path(r).suffix for r in bm if stem_key(r) == key)
        flag = ""
        if len(exts_b) > 1:
            flag = "  [ORPHAN/DUPLICATE: >1 file for this track]"
        elif exts_a and exts_b and exts_a != exts_b:
            flag = "  [replaced in place]"
        print(f"    {key[1]}  {exts_a} -> {exts_b}{flag}")

# ── PIONEER/USBANLZ ─────────────────────────────────────────────────────────
print("\n## PIONEER/USBANLZ")
ua, ub = a["usbanlz"], b["usbanlz"]
folders = sorted(set(ua) | set(ub))
any_anlz = False
for folder in folders:
    fa, fb = ua.get(folder), ub.get(folder)
    if fa is None or fb is None:
        print(f"  {folder}: present only in {'A' if fa else 'B'}")
        any_anlz = True
        continue
    lines = []
    for kind in sorted(set(fa) | set(fb)):
        ea, eb = fa.get(kind), fb.get(kind)
        if ea is None or eb is None:
            lines.append(f"    {kind}: present only in {'A' if ea else 'B'}")
            continue
        if ea["ppth"] != eb["ppth"]:
            lines.append(f"    {kind} PPTH: {ea['ppth']!r} -> {eb['ppth']!r}")
        types = {t["type"] for t in ea["tags"]} | {t["type"] for t in eb["tags"]}
        for ty in sorted(types):
            sa = [t["sha1"] for t in ea["tags"] if t["type"] == ty]
            sb = [t["sha1"] for t in eb["tags"] if t["type"] == ty]
            if sa != sb:
                lines.append(f"    {kind} {ty}: bytes changed")
        if ea.get("pqtz") != eb.get("pqtz"):
            lines.append(f"    {kind} PQTZ: {ea.get('pqtz')} -> {eb.get('pqtz')}")
        # cue lists, compared by (tag, time). A parse_error on either side means
        # the parsed cue list is unreliable (pyrekordbox cannot read some
        # CDJ-authored cue lists), so report the byte change without inventing
        # add/remove entries from an empty parse.
        if ea.get("parse_error") or eb.get("parse_error"):
            lines.append(f"    {kind} cue list unparseable "
                         f"(A_err={bool(ea.get('parse_error'))} "
                         f"B_err={bool(eb.get('parse_error'))}); see tag bytes above")
        else:
            ca = {(cl["tag"], e["time"]): e
                  for cl in ea.get("cue_lists", []) for e in cl["entries"]}
            cb = {(cl["tag"], e["time"]): e
                  for cl in eb.get("cue_lists", []) for e in cl["entries"]}
            for k in sorted(set(ca) - set(cb)):
                lines.append(f"    {kind} cue removed: {k[0]} @ {k[1]}ms")
            for k in sorted(set(cb) - set(ca)):
                e = cb[k]
                lines.append(f"    {kind} cue added: {k[0]} @ {k[1]}ms "
                             f"(type={e['type']} hot={e['hot_cue']})")
    if lines:
        any_anlz = True
        print(f"  {folder}:")
        print("\n".join(lines))
if not any_anlz:
    print("  (no change in any ANLZ set)")

# ── Device databases ────────────────────────────────────────────────────────
print("\n## Device databases (opaque blobs)")
da, dbb = a["device_dbs"], b["device_dbs"]
moved = False
for name in sorted(set(da) | set(dbb)):
    va, vb = da.get(name), dbb.get(name)
    if va == vb:
        continue
    moved = True
    if va is None:
        print(f"  {name}: created ({vb['size']} bytes)")
    elif vb is None:
        print(f"  {name}: deleted")
    else:
        note = "sha1 differs" if va["sha1"] != vb["sha1"] else "mtime only"
        print(f"  {name}: {va['size']}->{vb['size']} bytes, {note}")
if not moved:
    print("  (no change)")

# ── Device Library Plus (decrypted exportLibrary.db) ────────────────────────
pa, pb = a.get("dbplus"), b.get("dbplus")
if pa or pb:
    print("\n## Device Library Plus (exportLibrary.db, decrypted)")
    if not (pa and pb) or "error" in (pa or {}) or "error" in (pb or {}):
        print(f"  A={pa if not pa or 'error' in pa else 'ok'} "
              f"B={pb if not pb or 'error' in pb else 'ok'} (cannot compare)")
    else:
        # content rows keyed by masterContentId (desktop DjmdContent.ID)
        ca, cb = pa["content"], pb["content"]
        watch = ("fileType", "djPlayCount", "cueUpdateCount", "hasModified", "path")
        moved_p = False
        for mid in sorted(set(ca) | set(cb)):
            ra, rb_ = ca.get(mid), cb.get(mid)
            if ra is None or rb_ is None:
                print(f"  masterContentId={mid}: present only in {'A' if ra else 'B'}")
                moved_p = True
                continue
            deltas = [f"{k} {ra[k]!r}->{rb_[k]!r}" for k in watch if ra.get(k) != rb_.get(k)]
            if deltas:
                moved_p = True
                print(f"  masterContentId={mid} ({rb_['title']}): " + "; ".join(deltas))
        # cue rows keyed by (masterContentId, inUsec)
        ka = {(c["master_content_id"], c["inUsec"]): c for c in pa["cues"]}
        kb = {(c["master_content_id"], c["inUsec"]): c for c in pb["cues"]}
        for k in sorted(set(ka) - set(kb), key=lambda x: (str(x[0]), x[1] or 0)):
            moved_p = True
            print(f"  cue removed: masterContentId={k[0]} @ {k[1]}us (kind={ka[k]['kind']})")
        for k in sorted(set(kb) - set(ka), key=lambda x: (str(x[0]), x[1] or 0)):
            moved_p = True
            print(f"  cue added:   masterContentId={k[0]} @ {k[1]}us (kind={kb[k]['kind']})")
        if not moved_p:
            print("  (no change)")
