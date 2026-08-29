"""Profile the DjmdContent rows rekordbox writes for un-analyzed imports.

Splits a library into analyzed and un-analyzed tracks, then reports each
column's value distribution across the un-analyzed group. Those rows are what
an `import` command has to reproduce: rekordbox created them by scanning files it
never analyzed. Writes evidence/import-row-shape-<label>.json. Read-only.

    uv run python research/import-track-row-shape/scripts/import_row_shape.py <db_path> <label>

A column reported with one distinct value across every un-analyzed row is a
constant `import` can write verbatim; a column whose values vary comes from the
file or its tags.
"""

import json
import sys
from collections import Counter
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

if len(sys.argv) < 3:
    raise SystemExit("usage: import_row_shape.py <db_path> <label>")

db_path, label = sys.argv[1], sys.argv[2]
out_path = (
    Path(__file__).resolve().parent.parent / "evidence" / f"import-row-shape-{label}.json"
)

# Columns whose values are unique per track by construction; reporting their
# distribution says nothing, so they are profiled as "varies" without detail.
PER_TRACK = {
    "ID", "UUID", "FolderPath", "FileNameL", "Title", "MasterSongID",
    "rb_file_id", "rb_local_usn", "created_at", "updated_at", "FileSize",
}

# Identify the rekordbox installation rather than the import shape. They are
# constant per library, so recording them would leak an install ID into
# committed evidence for no analytical gain.
REDACT = {"DeviceID", "MasterDBID"}


def jsafe(v):
    return v if isinstance(v, (int, float, str, type(None))) else str(v)


db = Rekordbox6Database(path=db_path, unlock=True)
rows = db.session.query(tables.DjmdContent).all()
unanalyzed = [r for r in rows if r.Analysed == 0]
analyzed = [r for r in rows if r.Analysed != 0]

report = {
    "db": label,
    "total": len(rows),
    "unanalyzed": len(unanalyzed),
    "analyzed": len(analyzed),
    "constants": {},
    "varies": {},
}

for col in (c.key for c in tables.DjmdContent.__table__.columns):
    values = [getattr(r, col) for r in unanalyzed]
    if col in PER_TRACK:
        report["varies"][col] = {"distinct": len(set(map(jsafe, values)))}
        continue
    counts = Counter(jsafe(v) for v in values)
    if len(counts) == 1:
        report["constants"][col] = (
            "<redacted>" if col in REDACT else (values[0] if values else None)
        )
    else:
        report["varies"][col] = {
            "distinct": len(counts),
            "top": [[v, n] for v, n in counts.most_common(5)],
        }

out_path.write_text(json.dumps(report, indent=2, default=str))
print(f"{len(unanalyzed)} un-analyzed of {len(rows)} tracks -> {out_path.name}")
print(f"{len(report['constants'])} constant columns, {len(report['varies'])} varying")
db.close()
