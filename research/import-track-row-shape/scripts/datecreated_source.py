"""Test which filesystem timestamp rekordbox records as DateCreated.

Compares each un-analyzed track's DateCreated against its file's mtime and
birth time. Answers whether an `import` command should copy a file timestamp or
stamp the import date. Writes evidence/datecreated-source-<label>.json.
Read-only; skips tracks whose file is not mounted.

    uv run python research/import-track-row-shape/scripts/datecreated_source.py <db_path> <label>
"""

import datetime
import json
import os
import sys
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

if len(sys.argv) < 3:
    raise SystemExit("usage: datecreated_source.py <db_path> <label>")

db_path, label = sys.argv[1], sys.argv[2]
out_path = (
    Path(__file__).resolve().parent.parent
    / "evidence"
    / f"datecreated-source-{label}.json"
)

db = Rekordbox6Database(path=db_path, unlock=True)
unanalyzed = (
    db.session.query(tables.DjmdContent).filter(tables.DjmdContent.Analysed == 0).all()
)

tally = {"mtime_only": 0, "birthtime_only": 0, "both": 0, "neither": 0, "absent": 0}
samples = []
for row in unanalyzed:
    path = row.FolderPath or ""
    if not os.path.exists(path):
        tally["absent"] += 1
        continue
    st = os.stat(path)
    mtime = datetime.date.fromtimestamp(st.st_mtime).isoformat()
    # st_birthtime is macOS/BSD only; elsewhere it is absent.
    birth = getattr(st, "st_birthtime", None)
    birthtime = datetime.date.fromtimestamp(birth).isoformat() if birth else None

    hit_m, hit_b = row.DateCreated == mtime, row.DateCreated == birthtime
    if hit_m and hit_b:
        tally["both"] += 1
    elif hit_m:
        tally["mtime_only"] += 1
    elif hit_b:
        tally["birthtime_only"] += 1
    else:
        tally["neither"] += 1

    if len(samples) < 10:
        samples.append(
            {
                "ID": str(row.ID),
                "DateCreated": row.DateCreated,
                "mtime": mtime,
                "birthtime": birthtime,
            }
        )

out_path.write_text(
    json.dumps({"db": label, "checked": len(unanalyzed), "tally": tally,
                "samples": samples}, indent=2)
)
print(json.dumps(tally, indent=2))
print(f"-> {out_path.name}")
db.close()
