"""Snapshot the relational neighbourhood of one track for the edit-fields study.

Captures the subject `DjmdContent` row's relational foreign keys (Artist, Album,
Remixer, OrgArtist, Composer, Lyricist) and their proxy names, plus a full
census of `DjmdArtist` and `DjmdAlbum`. Every census row carries its name, its
`SearchStr`, the rekordbox sync bookkeeping (`UUID`, `rb_local_deleted`, `usn`,
`rb_local_usn`, timestamps), and a reference count computed across the library.

    uv run python research/edit-relational-fields/scripts/relational_snapshot.py <content_id> <stage>

Stage is a free label, e.g. e1-00-baseline, e1-10-postedit. Read-only; close
rekordbox first so the read sees committed state. Diff two stages with
relational_diff.py.

The reference counts are the load-bearing fields. `total_refs == 0` on a row
that still exists is an orphan; the `usn` / `rb_local_deleted` deltas reveal
whether an edit created, reused, soft-deleted, or left a shared record, which is
exactly what the apply logic must imitate.
"""

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb

if len(sys.argv) < 3:
    raise SystemExit("usage: relational_snapshot.py <content_id> <stage>")

cid, stage = sys.argv[1], sys.argv[2]
out_path = (
    Path(__file__).resolve().parent.parent / "evidence" / f"rel-{cid}-{stage}.json"
)

# Every DjmdContent column that points at a DjmdArtist row. Reference counting
# has to span all of them: a record orphaned as ArtistID may still be a Remixer.
ARTIST_ROLE_COLS = ("ArtistID", "RemixerID", "OrgArtistID", "ComposerID", "Lyricist")


def jsafe(v):
    return v if isinstance(v, (int, float, str, type(None))) else str(v)


db = Rekordbox6Database()

# ── Subject row ────────────────────────────────────────────────────────────
subject_row = db.get_content(ID=cid)
subject = {
    "ID": jsafe(subject_row.ID),
    "Title": jsafe(subject_row.Title),
    "ArtistID": jsafe(subject_row.ArtistID),
    "ArtistName": jsafe(subject_row.ArtistName),
    "AlbumID": jsafe(subject_row.AlbumID),
    "AlbumName": jsafe(subject_row.AlbumName),
    "AlbumArtistID": jsafe(getattr(subject_row.Album, "AlbumArtistID", None))
    if subject_row.Album is not None
    else None,
    "AlbumArtistName": jsafe(subject_row.AlbumArtistName),
    "RemixerID": jsafe(subject_row.RemixerID),
    "OrgArtistID": jsafe(subject_row.OrgArtistID),
    "ComposerID": jsafe(subject_row.ComposerID),
    "Lyricist": jsafe(subject_row.Lyricist),
}

# ── Reference counts across the whole library ──────────────────────────────
content_fk_rows = db.session.query(
    tb.DjmdContent.ArtistID,
    tb.DjmdContent.RemixerID,
    tb.DjmdContent.OrgArtistID,
    tb.DjmdContent.ComposerID,
    tb.DjmdContent.Lyricist,
    tb.DjmdContent.AlbumID,
).all()

artist_content_refs: Counter = Counter()
album_content_refs: Counter = Counter()
for artist_id, remixer_id, org_id, composer_id, lyricist_id, album_id in content_fk_rows:
    for role_id in (artist_id, remixer_id, org_id, composer_id, lyricist_id):
        if role_id is not None:
            artist_content_refs[role_id] += 1
    if album_id is not None:
        album_content_refs[album_id] += 1

album_rows = db.session.query(tb.DjmdAlbum).all()
artist_album_refs: Counter = Counter()
for album in album_rows:
    if album.AlbumArtistID is not None:
        artist_album_refs[album.AlbumArtistID] += 1

# ── Artist census ──────────────────────────────────────────────────────────
artist_rows = db.session.query(tb.DjmdArtist).all()
artists = []
for a in sorted(artist_rows, key=lambda r: str(r.ID)):
    content_refs = artist_content_refs.get(a.ID, 0)
    album_artist_refs = artist_album_refs.get(a.ID, 0)
    artists.append(
        {
            "ID": jsafe(a.ID),
            "Name": jsafe(a.Name),
            "SearchStr": jsafe(a.SearchStr),
            "UUID": jsafe(a.UUID),
            "rb_local_deleted": jsafe(a.rb_local_deleted),
            "usn": jsafe(a.usn),
            "rb_local_usn": jsafe(a.rb_local_usn),
            "created_at": jsafe(a.created_at),
            "updated_at": jsafe(a.updated_at),
            "content_refs": content_refs,
            "album_artist_refs": album_artist_refs,
            "total_refs": content_refs + album_artist_refs,
        }
    )

# ── Album census ───────────────────────────────────────────────────────────
albums = []
for al in sorted(album_rows, key=lambda r: str(r.ID)):
    albums.append(
        {
            "ID": jsafe(al.ID),
            "Name": jsafe(al.Name),
            "AlbumArtistID": jsafe(al.AlbumArtistID),
            "AlbumArtistName": jsafe(al.AlbumArtistName),
            "Compilation": jsafe(al.Compilation),
            "SearchStr": jsafe(al.SearchStr),
            "UUID": jsafe(al.UUID),
            "rb_local_deleted": jsafe(al.rb_local_deleted),
            "usn": jsafe(al.usn),
            "rb_local_usn": jsafe(al.rb_local_usn),
            "created_at": jsafe(al.created_at),
            "updated_at": jsafe(al.updated_at),
            "content_refs": album_content_refs.get(al.ID, 0),
        }
    )

db.close()

snapshot = {
    "content_id": cid,
    "stage": stage,
    "captured_at": datetime.now().isoformat(timespec="seconds"),
    "subject": subject,
    "totals": {
        "artists": len(artists),
        "albums": len(albums),
        "content": len(content_fk_rows),
    },
    "artists": artists,
    "albums": albums,
}

out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

orphan_artists = [a for a in artists if a["total_refs"] == 0]
orphan_albums = [a for a in albums if a["content_refs"] == 0]
print(f"Snapshot written: {out_path.name}")
print(
    f"  subject {subject['ID']}: Artist={subject['ArtistName']!r} "
    f"(ArtistID={subject['ArtistID']}) Album={subject['AlbumName']!r} "
    f"(AlbumID={subject['AlbumID']}, AlbumArtist={subject['AlbumArtistName']!r})"
)
print(
    f"  census: {len(artists)} artists ({len(orphan_artists)} orphaned), "
    f"{len(albums)} albums ({len(orphan_albums)} orphaned)"
)
