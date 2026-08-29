"""Census of FileType-by-extension and SearchStr population.

Two questions in one pass over a library:

1. Can a file extension determine a rekordbox FileType code? A `.m4a` holding
   ALAC and one holding AAC share an extension but not a code, so an `import`
   command that types files by suffix would mislabel one of them.
2. Does rekordbox populate SearchStr on any content, artist, or album row?

Writes evidence/filetype-searchstr-<label>.json. Read-only.

    uv run python research/import-track-row-shape/scripts/filetype_and_searchstr.py <db_path> <label>
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

if len(sys.argv) < 3:
    raise SystemExit("usage: filetype_and_searchstr.py <db_path> <label>")

db_path, label = sys.argv[1], sys.argv[2]
out_path = (
    Path(__file__).resolve().parent.parent
    / "evidence"
    / f"filetype-searchstr-{label}.json"
)

db = Rekordbox6Database(path=db_path, unlock=True)
session = db.session
rows = session.query(tables.DjmdContent).all()

by_extension: dict[str, dict[str, int]] = {}
for row in rows:
    ext = os.path.splitext(row.FileNameL or "")[1].lower()
    by_extension.setdefault(ext, {})
    key = str(row.FileType)
    by_extension[ext][key] = by_extension[ext].get(key, 0) + 1

ambiguous = {e: m for e, m in by_extension.items() if len(m) > 1}

searchstr = {}
for table, name in (
    (tables.DjmdContent, "DjmdContent"),
    (tables.DjmdArtist, "DjmdArtist"),
    (tables.DjmdAlbum, "DjmdAlbum"),
):
    total = session.query(table).count()
    populated = session.query(table).filter(table.SearchStr.isnot(None)).count()
    searchstr[name] = {"rows": total, "searchstr_populated": populated}

report = {
    "db": label,
    "file_type_by_extension": by_extension,
    "ambiguous_extensions": ambiguous,
    "searchstr": searchstr,
    "analysed_values": dict(Counter(str(r.Analysed) for r in rows)),
    "content_link_values": dict(Counter(str(r.ContentLink) for r in rows)),
}
out_path.write_text(json.dumps(report, indent=2))

print(json.dumps({"ambiguous_extensions": ambiguous, "searchstr": searchstr}, indent=2))
print(f"-> {out_path.name}")
db.close()
