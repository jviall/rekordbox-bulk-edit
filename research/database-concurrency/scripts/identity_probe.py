"""Same question, but through the ORM, which is how RBE actually reads rows.

get_filtered_content() returns mapped DjmdContent objects, so what the apply
pass sees depends on the identity map, not only on what SQLite returns.
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


db = Path("/tmp/rbe-probe-identity.db")
db.unlink(missing_ok=True)
engine = create_engine(f"sqlite:///{db}")
Base.metadata.create_all(engine)

raw = sqlite3.connect(db)
raw.execute("INSERT INTO t VALUES (1, 'before')")
raw.commit()
raw.close()

session = Session(engine)

preview = session.execute(select(Row)).scalars().all()
print(f"preview pass: {preview[0].Title!r}")

outside = sqlite3.connect(db, timeout=1)
outside.execute("UPDATE t SET Title = 'after' WHERE ID = 1")
outside.commit()
outside.close()

apply_pass = session.execute(select(Row)).scalars().all()
print(f"apply pass:   {apply_pass[0].Title!r}")
print(f"same object as preview: {apply_pass[0] is preview[0]}")

session.expire_all()
print(f"after expire_all: {session.execute(select(Row)).scalars().first().Title!r}")
session.close()
