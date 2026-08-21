"""Compare cue seek-info fields across source formats (FLAC vs MP3 vs AAC)."""

from collections import Counter

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

db = Rekordbox6Database()

cues = db.session.query(tables.DjmdCue).all()
by_content = Counter(c.ContentID for c in cues)

# Bucket cue-bearing contents by file type, pick the richest example of each.
best_per_type: dict[int, tuple[int, int]] = {}  # type -> (content_id, cue_count)
for cid, n in by_content.items():
    c = db.get_content(ID=cid)
    ft = c.FileType
    if ft not in best_per_type or n > best_per_type[ft][1]:
        best_per_type[ft] = (cid, n)

from rekordbox_edit.utils import get_file_type_name  # noqa: E402

for ft, (cid, n) in sorted(best_per_type.items()):
    c = db.get_content(ID=cid)
    print(f"\n===== FileType {ft} ({get_file_type_name(ft)}) ID={cid} "
          f"name={c.FileNameL!r} cues={n} =====")
    rows = db.session.query(tables.DjmdCue).filter_by(ContentID=cid).all()
    for r in rows[:8]:
        print(
            f"  Kind={r.Kind} InMsec={r.InMsec} InFrame={r.InFrame} "
            f"InMpegFrame={r.InMpegFrame} InMpegAbs={r.InMpegAbs} "
            f"CueMicrosec={r.CueMicrosec}"
        )
        print(f"      InPointSeekInfo={r.InPointSeekInfo!r} OutPointSeekInfo={r.OutPointSeekInfo!r}")

db.close()
