"""Diff two relational snapshots and print what an edit did to the graph.

    uv run python research/edit-relational-fields/scripts/relational_diff.py <content_id> <stageA> <stageB>

Reports the subject row's foreign-key moves, then the artist and album rows that
were created, removed, renamed, relinked, soft-deleted, or orphaned between the
two stages, with `usn` / `rb_local_usn` moves called out. Run it after each
rekordbox GUI edit to see exactly which shared records the edit touched and how.
"""

import json
import sys
from pathlib import Path

if len(sys.argv) < 4:
    raise SystemExit("usage: relational_diff.py <content_id> <stageA> <stageB>")

cid, stage_a, stage_b = sys.argv[1], sys.argv[2], sys.argv[3]
ev = Path(__file__).resolve().parent.parent / "evidence"

# Row fields whose change is worth reporting per surviving census row.
ARTIST_TRACKED = (
    "Name", "SearchStr", "rb_local_deleted", "usn", "rb_local_usn",
    "content_refs", "album_artist_refs", "total_refs",
)
ALBUM_TRACKED = (
    "Name", "AlbumArtistID", "AlbumArtistName", "Compilation", "SearchStr",
    "rb_local_deleted", "usn", "rb_local_usn", "content_refs",
)


def load(stage):
    p = ev / f"rel-{cid}-{stage}.json"
    if not p.exists():
        raise SystemExit(f"missing snapshot: {p.name}")
    return json.loads(p.read_text(encoding="utf-8"))


def index(rows):
    return {r["ID"]: r for r in rows}


def diff_census(label, a_rows, b_rows, tracked, ref_key):
    print(f"\n## {label}")
    a, b = index(a_rows), index(b_rows)
    added = [k for k in b if k not in a]
    removed = [k for k in a if k not in b]
    for k in added:
        r = b[k]
        print(
            f"  + created {k} Name={r['Name']!r} SearchStr={r['SearchStr']!r} "
            f"{ref_key}={r[ref_key]} usn={r['usn']} rb_local_usn={r['rb_local_usn']}"
        )
        if "AlbumArtistID" in r:
            print(f"      AlbumArtistID={r['AlbumArtistID']} ({r['AlbumArtistName']!r})")
    for k in removed:
        r = a[k]
        print(f"  - removed {k} Name={r['Name']!r} (was {ref_key}={r[ref_key]})")
    for k in a.keys() & b.keys():
        changes = [
            f"{f}: {a[k].get(f)!r} -> {b[k].get(f)!r}"
            for f in tracked
            if a[k].get(f) != b[k].get(f)
        ]
        if changes:
            print(f"  ~ {k} Name={b[k]['Name']!r}")
            for c in changes:
                print(f"      {c}")
        # Orphaned in place: still present, now referenced by nothing.
        if a[k].get(ref_key, 0) > 0 and b[k].get(ref_key, 0) == 0:
            print(
                f"      ORPHANED in place (rb_local_deleted="
                f"{b[k]['rb_local_deleted']})"
            )
    if not (added or removed) and all(
        all(a[k].get(f) == b[k].get(f) for f in tracked) for k in a.keys() & b.keys()
    ):
        print("  (no change)")


a, b = load(stage_a), load(stage_b)
print(f"# Relational diff content {cid}: {stage_a} -> {stage_b}")

print("\n## Subject row")
subj_changed = [
    (k, a["subject"].get(k), b["subject"].get(k))
    for k in b["subject"]
    if a["subject"].get(k) != b["subject"].get(k)
]
if subj_changed:
    for k, o, n in subj_changed:
        print(f"  {k}: {o!r} -> {n!r}")
else:
    print("  (no change)")

diff_census("Artists", a["artists"], b["artists"], ARTIST_TRACKED, "total_refs")
diff_census("Albums", a["albums"], b["albums"], ALBUM_TRACKED, "content_refs")

print("\n## Totals")
for k in b["totals"]:
    if a["totals"].get(k) != b["totals"].get(k):
        print(f"  {k}: {a['totals'].get(k)} -> {b['totals'].get(k)}")
