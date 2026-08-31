"""Spike: can the localUpdateCount read-modify-write be made atomic against a
concurrent writer, on the real SQLCipher engine pyrekordbox builds?

Two candidate shapes:
  read-then-write  - what autoincrement_local_update_count does today
  atomic UPDATE    - `SET int_1 = int_1 + n RETURNING int_1`, one statement

Run against a throwaway copy of the committed e2e fixture.
"""

import shutil
import sys
import threading
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from sqlalchemy import text

FIXTURE = Path("tests/e2e/fixtures/macos/master.6.8.6.db")
BUMPS = 25
WRITERS = 2

SELECT = text("SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'")
NAIVE = text(
    "UPDATE agentRegistry SET int_1 = :v WHERE registry_id = 'localUpdateCount'"
)
ATOMIC = text(
    "UPDATE agentRegistry SET int_1 = int_1 + 1 "
    "WHERE registry_id = 'localUpdateCount' RETURNING int_1"
)


def cleanup(path):
    # WAL mode leaves -wal and -shm beside the file; removing only the .db
    # would let a later copy inherit a previous run's committed pages.
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def make_copy(label):
    dst = Path(f"/tmp/usn-spike-{label}.db")
    cleanup(dst)
    shutil.copy(FIXTURE, dst)
    return dst


def writer(path, atomic, errors, stamps):
    db = Rekordbox6Database(path=str(path))
    try:
        for _ in range(BUMPS):
            try:
                if atomic:
                    new = db.session.execute(ATOMIC).scalar()
                    stamps.append(new)
                else:
                    saw = db.session.execute(SELECT).scalar()
                    db.session.execute(NAIVE, {"v": saw + 1})
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                errors.append(type(e).__name__)
    finally:
        db.close()


def run(label, atomic):
    path = make_copy(label)
    db = Rekordbox6Database(path=str(path))
    start = db.session.execute(SELECT).scalar()
    db.close()

    errors, stamps = [], []
    threads = [
        threading.Thread(target=writer, args=(path, atomic, errors, stamps))
        for _ in range(WRITERS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    db = Rekordbox6Database(path=str(path))
    final = db.session.execute(SELECT).scalar()
    db.close()
    cleanup(path)

    expected = start + BUMPS * WRITERS
    lost = expected - final
    print(f"  {label:<16} {start} -> {final} (expected {expected})")
    print(f"    {'OK' if lost == 0 else f'{lost} increment(s) LOST'}", end="")
    print(f", errors: {sorted(set(errors)) or 'none'}", end="")
    if atomic:
        dupes = len(stamps) - len(set(stamps))
        print(f", duplicate stamps handed out: {dupes}")
    else:
        print()


if not FIXTURE.is_file():
    sys.exit(f"fixture missing: {FIXTURE}")

print(f"{WRITERS} writers x {BUMPS} increments, real SQLCipher engine:")
run("read-then-write", atomic=False)
run("atomic-update", atomic=True)
