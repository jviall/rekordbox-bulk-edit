"""Classify every DjmdContent column by what fills it at import.

Produces the complete column-by-column contract an `import` command must satisfy:
for each of the table's columns, whether rekordbox fills it when it imports a
track, leaves it for analysis, or writes a fixed empty value. Any column this
script reports as `unclassified` is a gap in the design, not a column to ignore.

The analysis-owned set is not inferred from this library. It comes from the
zero-to-normal snapshot pair in ../../convert-reanalysis-impact/evidence/,
which observed one track before and after an analysis.

Writes evidence/column-coverage-<label>.json. Read-only.

    uv run python research/import-track-row-shape/scripts/column_coverage.py <db_path> <label>
"""

import json
import sys
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

if len(sys.argv) < 3:
    raise SystemExit("usage: column_coverage.py <db_path> <label>")

db_path, label = sys.argv[1], sys.argv[2]
out_path = (
    Path(__file__).resolve().parent.parent / "evidence" / f"column-coverage-{label}.json"
)

# Written by rekordbox's analysis pass, observed in the zero-to-normal diff.
# An import leaves every one of these at its zero value.
ANALYSIS_OWNED = {
    "Analysed", "AnalysisDataPath", "AnalysisUpdated", "TrackInfoUpdated",
    "BPM", "SampleRate", "BitDepth", "ContentLink",
}

# Filled from a tag at import AND overwritten by analysis. KeyID is the only
# column in both sets: an import reads the file's initialkey tag, and a later
# analysis replaces that value with its own computed key.
TAG_THEN_ANALYSIS = {"KeyID"}

# Set by pyrekordbox's add_content from the file and the library's device rows.
IDENTITY = {
    "ID", "UUID", "rb_file_id", "MasterSongID", "DeviceID", "MasterDBID",
    "FolderPath", "FileNameL", "FileSize", "StockDate",
}

# Read from the file's embedded tags or its stream header.
TAG_DERIVED = {
    "Title", "ArtistID", "AlbumID", "GenreID", "ComposerID", "LabelID",
    "TrackNo", "DiscNo", "ReleaseYear", "Commnt", "ISRC", "Length", "FileType",
}

# Derived from the file's timestamps rather than its contents.
FILE_STAT = {"DateCreated"}

# Bookkeeping columns SQLAlchemy or the USN registry maintain.
BOOKKEEPING = {"created_at", "updated_at", "rb_local_usn", "usn"}

# Identify the rekordbox installation rather than the import shape. They are
# constant per library, so recording them would leak an install ID into
# committed evidence for no analytical gain.
REDACT = {"DeviceID", "MasterDBID"}


def jsafe(v):
    return v if isinstance(v, (int, float, str, type(None))) else str(v)


db = Rekordbox6Database(path=db_path, unlock=True)
rows = (
    db.session.query(tables.DjmdContent).filter(tables.DjmdContent.Analysed == 0).all()
)
if not rows:
    raise SystemExit(f"{db_path} holds no un-analysed rows to profile")

report = {"db": label, "sampled_rows": len(rows), "columns": {}}
buckets: dict[str, list[str]] = {}

for col in (c.key for c in tables.DjmdContent.__table__.columns):
    values = [jsafe(getattr(r, col)) for r in rows]
    distinct = set(values)
    populated = sum(1 for v in values if v not in (None, "", 0, "0"))

    if col in TAG_THEN_ANALYSIS:
        kind = "tag_then_analysis"
    elif col in ANALYSIS_OWNED:
        kind = "analysis"
    elif col in IDENTITY:
        kind = "identity"
    elif col in TAG_DERIVED:
        kind = "tag"
    elif col in FILE_STAT:
        kind = "file_stat"
    elif col in BOOKKEEPING:
        kind = "bookkeeping"
    elif len(distinct) == 1:
        kind = "null_constant" if values[0] is None else "empty_constant"
    else:
        kind = "unclassified"

    entry = {"kind": kind, "populated": populated, "distinct": len(distinct)}
    # A single-valued column has a value worth recording; a varying one does not.
    if len(distinct) == 1:
        entry["value"] = "<redacted>" if col in REDACT else values[0]
    report["columns"][col] = entry
    buckets.setdefault(kind, []).append(col)

report["by_kind"] = {k: sorted(v) for k, v in sorted(buckets.items())}
out_path.write_text(json.dumps(report, indent=2))

total = len(report["columns"])
print(f"{total} columns over {len(rows)} un-analysed rows -> {out_path.name}\n")
for kind, cols in sorted(buckets.items()):
    print(f"  {kind:16} {len(cols):3}")
unclassified = buckets.get("unclassified", [])
print(f"\nunclassified: {unclassified or 'none'}")
db.close()
