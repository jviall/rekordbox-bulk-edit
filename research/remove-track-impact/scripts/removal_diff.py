"""Diff two removal snapshots and print what the arm changed.

    uv run python research/remove-track-impact/scripts/removal_diff.py <content_id> <stageA> <stageB>

Reports the subject row's fate (present, tombstoned, or gone), the columns that
moved on it, child rows cleared per table, shared records orphaned or collected,
the analysis directory and audio file, every census table whose count moved, and
the localUpdateCount delta.

The census delta is the honest check: it catches a table this study did not
think to watch, which is the failure mode a hand-written child-table list has.
"""

import json
import sys
from pathlib import Path

if len(sys.argv) < 4:
    raise SystemExit("usage: removal_diff.py <content_id> <stageA> <stageB>")

cid, stage_a, stage_b = sys.argv[1], sys.argv[2], sys.argv[3]
evidence = Path(__file__).resolve().parent.parent / "evidence"


def load(stage):
    path = evidence / f"rm-{cid}-{stage}.json"
    if not path.exists():
        raise SystemExit(f"missing snapshot: {path}")
    return json.loads(path.read_text())


a, b = load(stage_a), load(stage_b)

print(f"# {cid}: {stage_a} -> {stage_b}")
print(f"  {a['captured_at']} -> {b['captured_at']}")
print()

print("## Subject row")
if a["subject_present"] and not b["subject_present"]:
    print("  HARD DELETE: the DjmdContent row is gone from the table.")
elif a["subject_present"] and b["subject_present"]:
    deleted_flag = b["subject"].get("rb_local_deleted")
    if deleted_flag and not a["subject"].get("rb_local_deleted"):
        print(f"  TOMBSTONE: row still present, rb_local_deleted {a['subject'].get('rb_local_deleted')} -> {deleted_flag}.")
    else:
        print("  row still present.")
    moved = {
        k: (a["subject"].get(k), v)
        for k, v in b["subject"].items()
        if a["subject"].get(k) != v
    }
    if moved:
        for key, (old, new) in sorted(moved.items()):
            print(f"    {key}: {old!r} -> {new!r}")
    else:
        print("    no column changed.")
elif not a["subject_present"]:
    print("  subject was already absent in the baseline.")
print()

print("## Child rows")
tables = sorted(set(a["child_counts"]) | set(b["child_counts"]))
any_child = False
for name in tables:
    before, after = a["child_counts"].get(name, 0), b["child_counts"].get(name, 0)
    if before or after:
        any_child = True
        verdict = "cleared" if after == 0 and before else ("unchanged" if before == after else "changed")
        print(f"  {name:28} {before} -> {after}   {verdict}")
if not any_child:
    print("  the subject had no child rows in any ContentID table.")
print()

print("## Shared records the subject pointed at")
for label in sorted(set(a["relations"]) | set(b["relations"])):
    rel_a, rel_b = a["relations"].get(label), b["relations"].get(label)
    if rel_a is None and rel_b is None:
        continue
    if rel_a is None:
        print(f"  {label}: absent -> {rel_b}")
        continue
    name = rel_a["name"]
    if rel_b is None:
        # The subject is gone, so its FK no longer resolves; fall back to the
        # census delta below for whether the record itself survived.
        print(f"  {label:10} {name!r} (id {rel_a['id']}) had {rel_a['total_refs']} ref(s); "
              "subject row gone, see census")
        continue
    bits = []
    if rel_a["total_refs"] != rel_b["total_refs"]:
        bits.append(f"refs {rel_a['total_refs']} -> {rel_b['total_refs']}")
    if rel_a["exists"] != rel_b["exists"]:
        bits.append("COLLECTED" if not rel_b["exists"] else "appeared")
    if rel_a["rb_local_deleted"] != rel_b["rb_local_deleted"]:
        bits.append(f"rb_local_deleted {rel_a['rb_local_deleted']} -> {rel_b['rb_local_deleted']}")
    print(f"  {label:10} {name!r} (id {rel_a['id']}): " + (", ".join(bits) if bits else "unchanged"))
print()

print("## On disk")
an_a, an_b = a.get("analysis"), b.get("analysis")
if an_a:
    if an_b is None:
        print(f"  analysis dir {an_a['dir']}: subject gone, cannot re-resolve; check the path by hand")
    elif an_a["exists"] and not an_b["exists"]:
        print(f"  analysis dir REMOVED: {an_a['dir']}")
    elif an_a["exists"] and an_b["exists"]:
        names_a = {f["name"] for f in an_a["files"]}
        names_b = {f["name"] for f in an_b["files"]}
        gone, added = sorted(names_a - names_b), sorted(names_b - names_a)
        print(f"  analysis dir still present: {an_a['dir']}")
        if gone:
            print(f"    files removed: {gone}")
        if added:
            print(f"    files added:   {added}")
        if not gone and not added:
            print("    contents unchanged.")
    else:
        print(f"  analysis: {an_a.get('note') or 'none'}")

ar_a, ar_b = a.get("artwork"), b.get("artwork")
if ar_a:
    if ar_b is None:
        print(f"  artwork dir {ar_a['dir']}: subject gone, cannot re-resolve; check the path by hand")
    elif ar_a["exists"] and not ar_b["exists"]:
        print(f"  artwork dir REMOVED: {ar_a['dir']}")
    elif ar_a["exists"] and ar_b["exists"]:
        names_a = {f["name"] for f in ar_a["files"]}
        names_b = {f["name"] for f in ar_b["files"]}
        gone = sorted(names_a - names_b)
        print(f"  artwork dir still present: {ar_a['dir']}")
        if gone:
            print(f"    files removed: {gone}")
    else:
        print(f"  artwork: {ar_a.get('note') or 'none'}")

fa, fb = a["audio_file"], b["audio_file"]
if fa["exists"] and not fb["exists"]:
    print(f"  audio file DELETED: {fa['path']}")
elif fa["exists"] and fb["exists"]:
    print(f"  audio file kept: {fa['path']}")
else:
    print(f"  audio file absent in both stages: {fa['path']}")
print()

print("## Census")
moved_tables = False
for name in sorted(set(a["census"]) | set(b["census"])):
    before, after = a["census"].get(name), b["census"].get(name)
    if before != after:
        moved_tables = True
        print(f"  {name:28} {before} -> {after}   ({after - before:+d})")
if not moved_tables:
    print("  no table's row count moved.")

usn_a, usn_b = a["local_update_count"], b["local_update_count"]
print()
print(f"## localUpdateCount  {usn_a} -> {usn_b}"
      + (f"  ({int(usn_b) - int(usn_a):+d})" if usn_a is not None and usn_b is not None else ""))
