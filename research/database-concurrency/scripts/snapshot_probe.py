"""Does a repeat SELECT in one SQLAlchemy Session observe an outside commit?

Mirrors RBE's shape: one Session opened for the whole command, a first query
(the preview), a wait, then a second query (the apply pass), with a separate
connection committing in between. Uses plain SQLite in DELETE journal mode,
which is what pyrekordbox leaves master.db in.
"""

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

db = Path("/tmp/rbe-probe-snapshot.db")
db.unlink(missing_ok=True)

raw = sqlite3.connect(db)
raw.execute("CREATE TABLE t (ID INTEGER PRIMARY KEY, Title TEXT)")
raw.execute("INSERT INTO t VALUES (1, 'before')")
raw.commit()
raw.close()

engine = create_engine(f"sqlite:///{db}")
session = Session(engine)

first = session.execute(text("SELECT Title FROM t WHERE ID = 1")).scalar()
print(f"preview pass reads: {first!r}")

# An outside writer, standing in for Rekordbox.
outside = sqlite3.connect(db, timeout=1)
try:
    outside.execute("UPDATE t SET Title = 'after' WHERE ID = 1")
    outside.commit()
    print("outside writer committed")
except sqlite3.OperationalError as e:
    print(f"outside writer BLOCKED: {e}")
finally:
    outside.close()

second = session.execute(text("SELECT Title FROM t WHERE ID = 1")).scalar()
print(f"apply pass reads:   {second!r}")
print(f"in_transaction between passes: {session.in_transaction()}")
session.close()
