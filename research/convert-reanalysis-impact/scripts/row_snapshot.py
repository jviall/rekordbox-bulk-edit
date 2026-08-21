"""Snapshot a DjmdContent row to JSON and diff against the previous snapshot.

Read-only. Use it to discover which column rekordbox writes when you toggle a
feature in the app (for example the analysis/track Lock):

    1. uv run python research/convert-reanalysis-impact/scripts/row_snapshot.py <content_id>   # baseline
    2. toggle Lock on that track in rekordbox, then quit rekordbox
    3. uv run python research/convert-reanalysis-impact/scripts/row_snapshot.py <content_id>   # shows diff

The changed column is the one rekordbox uses for that feature.

Note: close rekordbox before snapshotting so the read sees committed state.
"""

import json
import sys
from pathlib import Path

from pyrekordbox import Rekordbox6Database

if len(sys.argv) < 2:
    raise SystemExit("usage: row_snapshot.py <content_id>")

cid = sys.argv[1]
snap_path = Path(__file__).resolve().parent.parent / "evidence" / f"row-snapshot-{cid}.json"

db = Rekordbox6Database()
c = db.get_content(ID=cid)
row = {col.name: getattr(c, col.name) for col in c.__table__.columns}
db.close()

# JSON-safe (datetimes, etc.)
row = {k: (v if isinstance(v, (int, float, str, type(None))) else str(v)) for k, v in row.items()}

if snap_path.exists():
    old = json.loads(snap_path.read_text(encoding="utf-8"))
    changed = {k: (old.get(k), row.get(k)) for k in row if old.get(k) != row.get(k)}
    if changed:
        print(f"Changed columns for content {cid} since last snapshot:")
        for k, (o, n) in changed.items():
            print(f"  {k}: {o!r} -> {n!r}")
    else:
        print(f"No columns changed for content {cid} since last snapshot.")
else:
    print(f"Baseline saved for content {cid} ({len(row)} columns).")

snap_path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Snapshot written: {snap_path}")
