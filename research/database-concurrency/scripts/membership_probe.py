"""Can the filtered set change even though loaded rows stay stale?

The WHERE clause runs in SQLite against live data; the identity map only
governs objects already loaded. This separates the two effects.
"""

import sqlite3
from pathlib import Path

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Row(Base):
    __tablename__ = "t"
    ID: Mapped[int] = mapped_column(primary_key=True)
    Title: Mapped[str] = mapped_column(String)


db = Path("/tmp/rbe-probe-membership.db")
db.unlink(missing_ok=True)
engine = create_engine(f"sqlite:///{db}")
Base.metadata.create_all(engine)

raw = sqlite3.connect(db)
raw.execute("INSERT INTO t VALUES (1, 'Burial - Archangel')")
raw.execute("INSERT INTO t VALUES (2, 'something else')")
raw.commit()
raw.close()

session = Session(engine)
stmt = select(Row).where(Row.Title.like("%Burial%"))

preview = session.execute(stmt).scalars().all()
print(f"preview matched: {[(r.ID, r.Title) for r in preview]}")

# Rekordbox renames row 2 so it now matches the same filter.
outside = sqlite3.connect(db, timeout=1)
outside.execute("UPDATE t SET Title = 'Burial - Shell of Light' WHERE ID = 2")
outside.commit()
outside.close()

apply_pass = session.execute(stmt).scalars().all()
print(f"apply matched:   {[(r.ID, r.Title) for r in apply_pass]}")
session.close()
