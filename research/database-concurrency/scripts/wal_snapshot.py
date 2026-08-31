"""Under WAL, does a transaction that has already read fail to upgrade to a
write after another connection commits (SQLITE_BUSY_SNAPSHOT), or succeed?

The answer decides whether the USN bump needs retry logic. Instrumented with
in_transaction() so a session that quietly closed its transaction cannot be
mistaken for one that held a snapshot across the outside commit.
"""

import shutil
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from sqlalchemy import text

FIXTURE = Path("tests/e2e/fixtures/macos/master.6.8.6.db")
SELECT = text("SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'")
RESERVE = text(
    "UPDATE agentRegistry SET int_1 = int_1 + :n "
    "WHERE registry_id = 'localUpdateCount' RETURNING int_1"
)


def cleanup(path):
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


path = Path("/tmp/wal-snapshot.db")
cleanup(path)
shutil.copy(FIXTURE, path)

ours = Rekordbox6Database(path=str(path))
theirs = Rekordbox6Database(path=str(path))

# Open our transaction with a real read, as get_filtered_content does.
tracks = ours.session.execute(text("SELECT ID FROM djmdContent LIMIT 5")).all()
opened_at = ours.session.execute(SELECT).scalar()
print(f"ours: read {len(tracks)} rows, counter {opened_at}, "
      f"in_transaction={ours.session.in_transaction()}")

theirs.session.execute(RESERVE, {"n": 3})
theirs.session.commit()
print(f"theirs: committed, counter now "
      f"{theirs.session.execute(SELECT).scalar()}")

print(f"ours: still in_transaction={ours.session.in_transaction()}")

try:
    high = ours.session.execute(RESERVE, {"n": 2}).scalar()
    ours.session.commit()
    print(f"ours: bump SUCCEEDED, high {high} "
          f"(fresh value + 2 = {opened_at + 3 + 2})")
except Exception as e:
    ours.session.rollback()
    print(f"ours: bump RAISED {type(e).__name__}: {str(e)[:120]}")

final = Rekordbox6Database(path=str(path))
print(f"final counter {final.session.execute(SELECT).scalar()}, "
      f"expected {opened_at + 5}")
for db in (ours, theirs, final):
    db.close()
cleanup(path)
