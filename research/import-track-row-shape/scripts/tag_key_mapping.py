"""Derive which tag key rekordbox reads for each column, per container format.

A tag library's normalized ("easy") interface cannot answer this. Its key
coverage differs by format, so it silently drops ISRC on MP4 and comments on
MP3. Reproducing an import needs the real per-format keys, and this script
recovers them from evidence rather than from a specification.

Method: for every un-analyzed track, compare the value rekordbox stored in a
column against every raw tag in the file. A tag whose value matches is a
candidate source for that column. Matching runs over decoded bytes and over
substrings, because MP4 freeform atoms hold bytes and the `xid ` atom wraps an
ISRC as "<vendor>:isrc:<value>".

The negative result matters as much as the positive one. A tag present in the
file while its column stays empty is proof rekordbox ignores that tag.

Writes evidence/tag-key-mapping-<label>.json. Read-only, and reads the audio
files themselves, so the library's volume must be mounted.

    uv run python research/import-track-row-shape/scripts/tag_key_mapping.py <db_path> <label>
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import mutagen
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

if len(sys.argv) < 3:
    raise SystemExit("usage: tag_key_mapping.py <db_path> <label>")

db_path, label = sys.argv[1], sys.argv[2]
out_path = (
    Path(__file__).resolve().parent.parent / "evidence" / f"tag-key-mapping-{label}.json"
)

FORMAT_NAMES = {1: "MP3", 4: "AAC", 5: "FLAC", 6: "ALAC", 11: "WAV", 12: "AIFF"}

# Tags that, if present while the column stays empty, prove rekordbox ignores
# them. Checked per format.
IGNORE_PROBES = {"KeyID": "----:com.apple.iTunes:initialkey"}


def tag_strings(tags, key):
    """Every string form a tag value may take, including decoded freeform bytes."""
    out = []
    try:
        raw = tags[key]
    except Exception:
        return out
    for value in raw if isinstance(raw, list) else [raw]:
        if isinstance(value, (bytes, bytearray)):
            out.append(bytes(value).decode("utf-8", "replace"))
            continue
        out.append(str(value))
        try:
            out.append(bytes(value).decode("utf-8", "replace"))
        except Exception:
            pass
    return out


db = Rekordbox6Database(path=db_path, unlock=True)
session = db.session
rows = (
    session.query(tables.DjmdContent).filter(tables.DjmdContent.Analysed == 0).all()
)


def related(table, id_):
    if not id_ or id_ == "0":
        return ""
    row = session.query(table).filter_by(ID=id_).first()
    return (row.Name if table is not tables.DjmdKey else row.ScaleName) if row else ""


exact = defaultdict(lambda: defaultdict(Counter))
substring = defaultdict(lambda: defaultdict(Counter))
unmatched = defaultdict(Counter)
ignored = defaultdict(Counter)
scanned = Counter()

for row in rows:
    fmt = FORMAT_NAMES.get(row.FileType, str(row.FileType))
    try:
        audio = mutagen.File(row.FolderPath or "")
    except Exception:
        continue
    if audio is None or not audio.tags:
        continue
    scanned[fmt] += 1

    columns = {
        "Title": row.Title or "",
        "Commnt": row.Commnt or "",
        "ISRC": row.ISRC or "",
        "ComposerID": related(tables.DjmdArtist, row.ComposerID),
        "ArtistID": related(tables.DjmdArtist, row.ArtistID),
        "AlbumID": related(tables.DjmdAlbum, row.AlbumID),
        "GenreID": related(tables.DjmdGenre, row.GenreID),
        "LabelID": related(tables.DjmdLabel, row.LabelID),
        "KeyID": related(tables.DjmdKey, row.KeyID),
    }

    keys = list(audio.tags.keys())
    for column, want in columns.items():
        if not want:
            # An ignored-tag probe: the tag is present, the column is empty.
            probe = IGNORE_PROBES.get(column)
            if probe and probe in keys:
                ignored[fmt][f"{column} <- {probe}"] += 1
            continue
        hit = False
        for key in keys:
            values = tag_strings(audio.tags, key)
            if any(v.strip() == want.strip() for v in values):
                exact[fmt][column][str(key)] += 1
                hit = True
            elif any(want.strip() and want.strip() in v for v in values):
                substring[fmt][column][str(key)] += 1
                hit = True
        if not hit:
            unmatched[fmt][column] += 1

report = {
    "db": label,
    "scanned_by_format": dict(scanned),
    "exact_match": {f: {c: dict(k) for c, k in cols.items()} for f, cols in exact.items()},
    "substring_match": {
        f: {c: dict(k) for c, k in cols.items()} for f, cols in substring.items()
    },
    "column_populated_no_tag_matched": {f: dict(c) for f, c in unmatched.items()},
    "tag_present_column_empty": {f: dict(c) for f, c in ignored.items()},
}
out_path.write_text(json.dumps(report, indent=2))

for fmt in sorted(exact):
    print(f"--- {fmt} ({scanned[fmt]} files) ---")
    for column, counts in sorted(exact[fmt].items()):
        top = ", ".join(f"{k} ({n})" for k, n in counts.most_common(2))
        print(f"   {column:12} <- {top}")
    for column, counts in sorted(substring[fmt].items()):
        top = ", ".join(f"{k} ({n})" for k, n in counts.most_common(2))
        print(f"   {column:12} <~ {top}  (substring)")
    if ignored.get(fmt):
        print(f"   IGNORED: {dict(ignored[fmt])}")
    print()
print(f"-> {out_path.name}")
db.close()
