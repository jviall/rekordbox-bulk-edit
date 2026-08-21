"""Inspect DjmdContent audio-coupled columns vs what convert updates."""

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

db = Rekordbox6Database()

cols = [c.name for c in tables.DjmdContent.__table__.columns]
interesting = [c for c in cols if any(k in c.lower() for k in (
    "file", "folder", "path", "rate", "depth", "bit", "length", "size",
    "analy", "anlz", "org", "kind", "format"))]
print("Audio/file-coupled DjmdContent columns:")
print(interesting)

print("\nExample values (real MP3 ID=131718786):")
c = db.get_content(ID=131718786)
for col in interesting:
    print(f"   {col} = {getattr(c, col, '<n/a>')!r}")

# Columns convert.py writes (from source): SampleRate, BitDepth, BitRate,
# FileType, FileNameL, FolderPath
written = {"SampleRate", "BitDepth", "BitRate", "FileType", "FileNameL", "FolderPath"}
print("\nConvert WRITES:", sorted(written))
print("Potentially-stale audio/file columns convert does NOT write:")
print(sorted(set(interesting) - written))

db.close()
