"""Two follow-ups to the atomic-increment spike.

1. Block reservation: a commit buffers N changes, so the counter must advance
   by N in one statement and hand back the block.
2. The realistic transaction shape: RBE's transaction opens with a read (the
   filter query), and an outside writer may commit before the counter bump.
   Does the bump then fail, or silently compute from the current value?
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
    # WAL mode leaves -wal and -shm beside the file; removing only the .db
    # would let a later copy inherit a previous run's committed pages.
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def copy(label):
    dst = Path(f"/tmp/usn-spike2-{label}.db")
    cleanup(dst)
    shutil.copy(FIXTURE, dst)
    return dst


print("1. Reserving a block of N in one statement")
path = copy("block")
db = Rekordbox6Database(path=str(path))
start = db.session.execute(SELECT).scalar()
high = db.session.execute(RESERVE, {"n": 7}).scalar()
db.session.commit()
print(f"   start {start}, reserved 7, high {high}")
print(f"   stamps for this commit: {list(range(high - 7 + 1, high + 1))}")
print(f"   contiguous and ending at the counter: {high == start + 7}")
db.close()
path.unlink(missing_ok=True)

print("\n2. Outside writer commits after our transaction opened with a read")
path = copy("interleave")
ours = Rekordbox6Database(path=str(path))
theirs = Rekordbox6Database(path=str(path))

opened_at = ours.session.execute(SELECT).scalar()
print(f"   our read at transaction open: {opened_at}")

theirs.session.execute(RESERVE, {"n": 3})
theirs.session.commit()
after_theirs = theirs.session.execute(SELECT).scalar()
print(f"   outside writer committed, counter now {after_theirs}")

try:
    high = ours.session.execute(RESERVE, {"n": 2}).scalar()
    ours.session.commit()
    print(f"   our bump succeeded, high {high}")
    print(f"   computed from the fresh value, not our stale read: {high == after_theirs + 2}")
except Exception as e:
    ours.session.rollback()
    print(f"   our bump RAISED {type(e).__name__}: {str(e)[:90]}")

final = ours.session.execute(SELECT).scalar()
print(f"   final counter {final}, expected {opened_at + 5} -> "
      f"{'OK' if final == opened_at + 5 else 'LOST'}")
ours.close()
theirs.close()
path.unlink(missing_ok=True)
