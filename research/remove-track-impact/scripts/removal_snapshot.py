"""Snapshot everything a track removal could touch, for the remove-command study.

Captures the subject `DjmdContent` row in full, every child row in every table
carrying a `ContentID`, the shared relational records the subject points at with
their library-wide reference counts, the on-disk analysis directory and audio
file, and the global row census plus `localUpdateCount`.

    uv run python research/remove-track-impact/scripts/removal_snapshot.py <content_id> <stage>

Stage is a free label, e.g. r1-00-baseline, r1-10-removed. Read-only; close
rekordbox first so the read sees committed state. Diff two stages with
removal_diff.py.

The load-bearing fields are `rb_local_deleted` and the global census. A subject
row still present with `rb_local_deleted == 1` is a tombstone; a row gone from
the census is a hard delete. The `total_refs` counts show whether removal
orphans a shared record and whether rekordbox then collects it, and the
per-table census catches a child row cleared in a table the subject was not
known to occupy.

Pass the library with RBE_DATABASE_PATH; it defaults to the GIG MUSIC test
library rather than the maintainer's real one, because every arm of this study
destroys state.
"""

import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb

DEFAULT_DB = "/Volumes/GIG MUSIC/PIONEER/Master/master.db"

if len(sys.argv) < 3:
    raise SystemExit("usage: removal_snapshot.py <content_id> <stage>")

cid, stage = sys.argv[1], sys.argv[2]
out_path = (
    Path(__file__).resolve().parent.parent / "evidence" / f"rm-{cid}-{stage}.json"
)

# Every DjmdContent column that points at a DjmdArtist row. An artist is
# orphaned only when none of these, nor any album's AlbumArtistID, still
# reference it.
ARTIST_ROLE_COLS = ("ArtistID", "RemixerID", "OrgArtistID", "ComposerID", "Lyricist")


def jsafe(v):
    return v if isinstance(v, (int, float, str, type(None))) else str(v)


def row_dict(row):
    return {c.name: jsafe(getattr(row, c.name)) for c in row.__table__.columns}


def child_tables():
    """Every mapped table carrying a ContentID column, in name order."""
    found = []
    for obj in vars(tb).values():
        table = getattr(obj, "__table__", None)
        if table is None or not isinstance(obj, type):
            continue
        if any(c.name == "ContentID" for c in table.columns):
            found.append(obj)
    return sorted(set(found), key=lambda m: m.__tablename__)


def census_tables():
    """Every mapped table, for the global row census."""
    found = {}
    for obj in vars(tb).values():
        table = getattr(obj, "__table__", None)
        if table is not None and isinstance(obj, type):
            found[obj.__tablename__] = obj
    return dict(sorted(found.items()))


def file_digest(path: Path):
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return None


def anlz_snapshot(db, content):
    """The subject's analysis directory, or why there is none.

    Guarded on AnalysisDataPath: pyrekordbox's get_anlz_dir strips the leading
    separator and joins the remainder onto the share directory, so an empty
    AnalysisDataPath resolves to the share root itself rather than to a
    per-track directory. Reporting that path as the subject's would be wrong,
    and acting on it would be destructive.
    """
    if not content.AnalysisDataPath:
        return {"analysis_data_path": content.AnalysisDataPath, "dir": None,
                "exists": False, "files": [], "note": "no analysis"}
    anlz_dir = db.get_anlz_dir(content)
    files = []
    if anlz_dir.is_dir():
        for entry in sorted(anlz_dir.iterdir()):
            files.append({
                "name": entry.name,
                "size": entry.stat().st_size if entry.is_file() else None,
                "sha1": file_digest(entry) if entry.is_file() else None,
            })
    return {
        "analysis_data_path": content.AnalysisDataPath,
        "dir": str(anlz_dir),
        "exists": anlz_dir.is_dir(),
        "files": files,
    }


def artwork_snapshot(db, session, content):
    """The subject's artwork directory, or why there is none.

    Artwork is the second per-track on-disk artifact, parallel to the analysis
    directory: `ImagePath` holds a device-relative path under
    `share/PIONEER/Artwork/`, keyed by the same content UUID, holding
    artwork.jpg with its _s and _m thumbnails. It is guarded the same way an
    empty AnalysisDataPath is, and for the same reason.

    `shared_with` counts other content rows naming the same path. Removal may
    only delete the files when nothing else points at them, and this library
    cannot settle whether rekordbox ever shares one: only two of its rows carry
    an ImagePath at all.
    """
    if not content.ImagePath:
        return {"image_path": content.ImagePath, "dir": None, "exists": False,
                "files": [], "shared_with": 0, "note": "no artwork"}
    art_path = Path(db._share_dir) / content.ImagePath.strip("\\/")
    art_dir = art_path.parent
    files = []
    if art_dir.is_dir():
        for entry in sorted(art_dir.iterdir()):
            files.append({
                "name": entry.name,
                "size": entry.stat().st_size if entry.is_file() else None,
                "sha1": file_digest(entry) if entry.is_file() else None,
            })
    shared = (
        session.query(tb.DjmdContent)
        .filter(tb.DjmdContent.ImagePath == content.ImagePath)
        .filter(tb.DjmdContent.ID != content.ID)
        .count()
    )
    return {
        "image_path": content.ImagePath,
        "file": str(art_path),
        "dir": str(art_dir),
        "exists": art_dir.is_dir(),
        "files": files,
        "shared_with": shared,
    }


def prior_paths(cid, stage):
    """The subject's three file paths, recovered from an earlier snapshot.

    A removed row cannot tell us where its files were, so a post-removal
    snapshot has nothing to stat and would report every artifact as absent
    whether or not it survived. The paths come from the most recent earlier
    snapshot of the same track instead, which is what makes "the file was kept"
    and "the row is gone" separable observations.
    """
    candidates = sorted(
        (path for path in out_path.parent.glob(f"rm-{cid}-*.json") if path.name != f"rm-{cid}-{stage}.json"),
        key=lambda path: path.stat().st_mtime,
    )
    for path in reversed(candidates):
        data = json.loads(path.read_text())
        if data.get("subject"):
            return {
                "source_stage": data["stage"],
                "FolderPath": data["subject"].get("FolderPath"),
                "AnalysisDataPath": data["subject"].get("AnalysisDataPath"),
                "ImagePath": data["subject"].get("ImagePath"),
            }
    return None


db = Rekordbox6Database(path=os.environ.get("RBE_DATABASE_PATH", DEFAULT_DB))
session = db.session

content = session.query(tb.DjmdContent).filter_by(ID=cid).one_or_none()
recovered = prior_paths(cid, stage) if content is None else None

# Reference counts span the whole library, so a record the subject vacates is
# only an orphan when nothing else anywhere still points at it.
artist_refs, album_refs, genre_refs, label_refs, key_refs = (Counter() for _ in range(5))
for row in session.query(tb.DjmdContent).all():
    for col in ARTIST_ROLE_COLS:
        value = getattr(row, col, None)
        if value:
            artist_refs[str(value)] += 1
    for value, counter in (
        (row.AlbumID, album_refs),
        (row.GenreID, genre_refs),
        (row.LabelID, label_refs),
        (row.KeyID, key_refs),
    ):
        if value:
            counter[str(value)] += 1
for album in session.query(tb.DjmdAlbum).all():
    if album.AlbumArtistID:
        artist_refs[str(album.AlbumArtistID)] += 1

RELATIONS = (
    ("artist", "ArtistID", tb.DjmdArtist, artist_refs),
    ("album", "AlbumID", tb.DjmdAlbum, album_refs),
    ("genre", "GenreID", tb.DjmdGenre, genre_refs),
    ("label", "LabelID", tb.DjmdLabel, label_refs),
    ("key", "KeyID", tb.DjmdKey, key_refs),
    ("remixer", "RemixerID", tb.DjmdArtist, artist_refs),
    ("orgartist", "OrgArtistID", tb.DjmdArtist, artist_refs),
    ("composer", "ComposerID", tb.DjmdArtist, artist_refs),
)

relations = {}
if content is not None:
    for label, column, model, refs in RELATIONS:
        fk = getattr(content, column, None)
        if not fk:
            relations[label] = None
            continue
        row = session.query(model).filter_by(ID=fk).one_or_none()
        relations[label] = {
            "column": column,
            "id": str(fk),
            # DjmdKey calls its label ScaleName; every other relation uses Name.
            "name": jsafe(
                getattr(row, "Name", None) or getattr(row, "ScaleName", None)
            )
            if row is not None
            else None,
            "exists": row is not None,
            "total_refs": refs[str(fk)],
            "rb_local_deleted": jsafe(getattr(row, "rb_local_deleted", None)),
            "rb_local_usn": jsafe(getattr(row, "rb_local_usn", None)),
        }

children = {}
for model in child_tables():
    rows = session.query(model).filter(model.ContentID == cid).all()
    children[model.__tablename__] = [row_dict(r) for r in rows]

registry = (
    session.query(tb.AgentRegistry).filter_by(registry_id="localUpdateCount").one_or_none()
)

def share_relative(fragment):
    """Resolve a device-relative rekordbox path against the share directory."""
    return Path(db._share_dir) / fragment.strip("\\/")


if content is not None:
    audio_path = Path(content.FolderPath) if content.FolderPath else None
elif recovered and recovered["FolderPath"]:
    audio_path = Path(recovered["FolderPath"])
else:
    audio_path = None


def recovered_dir_snapshot(fragment, kind):
    """Report a removed subject's analysis or artwork directory by stat alone."""
    if not fragment:
        return {"dir": None, "exists": False, "files": [], "note": f"no {kind}"}
    target = share_relative(fragment).parent
    files = []
    if target.is_dir():
        for entry in sorted(target.iterdir()):
            files.append({
                "name": entry.name,
                "size": entry.stat().st_size if entry.is_file() else None,
                "sha1": file_digest(entry) if entry.is_file() else None,
            })
    return {
        "dir": str(target),
        "exists": target.is_dir(),
        "parent_exists": target.parent.is_dir(),
        "files": files,
        "resolved_from": recovered["source_stage"],
    }

snapshot = {
    "content_id": cid,
    "stage": stage,
    "captured_at": datetime.now().isoformat(timespec="seconds"),
    "database": str(getattr(db, "db_dir", None) or db.db_directory),
    "subject_present": content is not None,
    "subject": row_dict(content) if content is not None else None,
    "audio_file": {
        "path": str(audio_path) if audio_path else None,
        "exists": audio_path.exists() if audio_path else False,
        "size": audio_path.stat().st_size if audio_path and audio_path.exists() else None,
    },
    "analysis": (
        anlz_snapshot(db, content)
        if content is not None
        else (recovered_dir_snapshot(recovered["AnalysisDataPath"], "analysis") if recovered else None)
    ),
    "artwork": (
        artwork_snapshot(db, session, content)
        if content is not None
        else (recovered_dir_snapshot(recovered["ImagePath"], "artwork") if recovered else None)
    ),
    "recovered_paths": recovered,
    "relations": relations,
    "children": children,
    "child_counts": {name: len(rows) for name, rows in children.items()},
    "census": {
        name: session.query(model).count() for name, model in census_tables().items()
    },
    "local_update_count": jsafe(registry.int_1) if registry is not None else None,
}

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
db.close()

print(f"wrote {out_path}")
print(f"  subject present: {snapshot['subject_present']}")
if content is not None:
    print(f"  rb_local_deleted: {snapshot['subject']['rb_local_deleted']}"
          f"  rb_local_usn: {snapshot['subject']['rb_local_usn']}")
print(f"  child rows: {sum(snapshot['child_counts'].values())} "
      f"across {sum(1 for n in snapshot['child_counts'].values() if n)} table(s)")
print(f"  analysis dir exists: {snapshot['analysis']['exists'] if snapshot['analysis'] else None}")
print(f"  artwork dir exists: {snapshot['artwork']['exists'] if snapshot['artwork'] else None}"
      + (f" (shared with {snapshot['artwork']['shared_with']} other row(s))"
         if snapshot['artwork'] and snapshot['artwork'].get('shared_with') is not None
         and snapshot['artwork']['exists'] else ""))
print(f"  audio file exists: {snapshot['audio_file']['exists']}")
print(f"  localUpdateCount: {snapshot['local_update_count']}")
