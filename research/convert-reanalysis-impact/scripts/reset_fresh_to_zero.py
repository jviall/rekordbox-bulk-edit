"""Reset the fresh Phase-1 fixtures (F1 Immigrant, F2 Pregonando) to Analysed=0.

Resolves each fixture's current ANLZ folder from the live database, deletes that
per-track folder, then copies the zero-state master.db back over the live one.
This restores the identical pre-analysis input for the next determinism run.

Run with rekordbox closed. Safe: it deletes only the two fixtures' own UUID
folders and restores from A:/rb-convert-test-backup/exp2/master-zero.db.

    uv run python research/convert-reanalysis-impact/scripts/reset_fresh_to_zero.py
"""

import shutil
from pathlib import Path

from pyrekordbox import Rekordbox6Database

RB = Path(r"C:/Users/rbe-test/AppData/Roaming/Pioneer/rekordbox")
ZERO = Path(r"A:/rb-convert-test-backup/exp2/master-zero.db")
FIXTURES = ["27790898", "174954387"]  # F1 Immigrant, F2 Pregonando

db = Rekordbox6Database()
folders = set()
for cid in FIXTURES:
    for _kind, p in db.get_anlz_paths(cid).items():
        if p:
            folders.add(Path(p).parent)
db.close()

for f in sorted(folders):
    if f.exists():
        shutil.rmtree(f)
        print(f"deleted ANLZ folder: {f}")
if not folders:
    print("no ANLZ folders to delete (already at zero)")

shutil.copy2(ZERO, RB / "master.db")
print("restored master.db from master-zero.db")
