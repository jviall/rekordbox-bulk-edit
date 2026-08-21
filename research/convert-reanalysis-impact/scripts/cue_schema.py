"""Explore DjmdCue schema and find tracks with the most cues."""

from collections import Counter

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

db = Rekordbox6Database()

# Schema of DjmdCue
print("== DjmdCue columns ==")
print([c.name for c in tables.DjmdCue.__table__.columns])

cues = db.session.query(tables.DjmdCue).all()
print(f"\nTotal DjmdCue rows: {len(cues)}")

by_content = Counter(c.ContentID for c in cues)
print(f"Distinct contents with cues: {len(by_content)}")
print("\nTop 8 contents by cue count:")
for cid, n in by_content.most_common(8):
    c = db.get_content(ID=cid)
    print(f"  ID={cid} cues={n} type={c.FileType} name={c.FileNameL!r} len={c.Length}")

# Dump a sample of cue rows for the richest track
if by_content:
    top_cid = by_content.most_common(1)[0][0]
    print(f"\n== Sample DjmdCue rows for ID={top_cid} ==")
    rows = db.session.query(tables.DjmdCue).filter_by(ContentID=top_cid).all()
    for r in rows[:12]:
        print(
            f"  Kind={r.Kind} InMsec={r.InMsec} InFrame={r.InFrame} "
            f"OutMsec={r.OutMsec} OutFrame={r.OutFrame} "
            f"Color={getattr(r, 'ColorTableIndex', None)} ActiveLoop={getattr(r, 'ActiveLoop', None)}"
        )

db.close()
