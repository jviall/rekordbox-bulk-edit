"""End-to-end: `remove` against a real database and a real share tree.

Every test drives the installed CLI against a private DB copy, so removals
never disturb the ordered journey suite. The committed fixture ships the
database alone; the analysis and artwork directories `remove` deletes are
materialized under that copy's own share directory by `share_tree`, at the
paths the fixture rows already record.

Removing a track is the one operation here that reaches outside the database
on its own, so the assertions are as much about what survives — a sibling's
artwork, a shared artist, the source audio — as about what goes.
"""

import json
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb

from tests.e2e.conftest import AUDIO_DIR, STAGED_AUDIO_DIR, CliRun

pytestmark = pytest.mark.e2e

# Titles the fixture DB carries, chosen for what each one selects:
GAMMA_ONLY = "Interchange"  # Gamma's and AIFF Sampler's only track
SHARED_ARTIST = "Apple Alpha"  # shares artist Alpha with Wave Alpha
NO_ARTWORK = "Üñîcödé Mañana"  # the one row with an empty ImagePath
SOURCE_DELETE = "Studio Master"  # 06-wav-96k-24b.wav, untouched by other tests

# Rekordbox writes the full-size image plus two thumbnails into each track's
# artwork directory; a removal takes all three.
ARTWORK_FILES = ("artwork.jpg", "artwork_m.jpg", "artwork_s.jpg")


@dataclass(frozen=True)
class Row:
    """What a fixture row records about itself and its files on disk."""

    id: str
    analysis_dir: Path | None
    artwork_dir: Path | None
    source: Path


def _load(p: subprocess.CompletedProcess[str]) -> dict:
    assert p.returncode == 0, f"non-zero exit ({p.returncode}); stderr:\n{p.stderr}"
    return json.loads(p.stdout)


def _titles(rbe: CliRun) -> list[str]:
    return [t["Title"] for t in _load(rbe("search", "--print", "json"))["tracks"]]


@pytest.fixture
def share_dir(fresh_db: Path) -> Path:
    """pyrekordbox derives the share directory as `<db_dir>/share`."""
    return fresh_db.parent / "share"


@pytest.fixture
def rows(fresh_db: Path, share_dir: Path) -> dict[str, Row]:
    """Every fixture row by title, with the directories its paths resolve to."""
    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    by_title = {}
    for content in db.session.query(tb.DjmdContent).all():
        by_title[content.Title] = Row(
            id=str(content.ID),
            analysis_dir=(
                share_dir / Path(content.AnalysisDataPath.strip("/")).parent
                if content.AnalysisDataPath
                else None
            ),
            artwork_dir=(
                share_dir / Path(content.ImagePath.strip("/")).parent
                if content.ImagePath
                else None
            ),
            source=Path(content.FolderPath),
        )
    db.close()
    return by_title


@pytest.fixture
def share_tree(share_dir: Path, rows: dict[str, Row]) -> Path:
    """Create the analysis and artwork files the fixture rows point at.

    A real library's share tree is far too large to commit, and the fixture
    carries only the database, so the files are synthesized here from the
    stored paths. Content does not matter: `remove` deletes by path.
    """
    for row in rows.values():
        if row.analysis_dir is not None:
            row.analysis_dir.mkdir(parents=True, exist_ok=True)
            (row.analysis_dir / "ANLZ0000.DAT").write_bytes(b"PMAI")
        if row.artwork_dir is not None:
            row.artwork_dir.mkdir(parents=True, exist_ok=True)
            for name in ARTWORK_FILES:
                (row.artwork_dir / name).write_bytes(b"\xff\xd8\xff")
    return share_dir


@pytest.fixture
def restore_staged_audio() -> Iterator[None]:
    """Put back any staged audio a test deletes.

    The fixture rows record FolderPath under the session-wide staged
    directory, which the journey suite also reads, so `--delete-source`
    deletes a file other tests depend on.
    """
    yield
    for src in AUDIO_DIR.iterdir():
        if src.is_file() and not (STAGED_AUDIO_DIR / src.name).exists():
            shutil.copy(src, STAGED_AUDIO_DIR / src.name)


def test_unfiltered_remove_is_refused(rbe: CliRun):
    """An unfiltered write would match the whole library, and remove cannot
    be undone."""
    result = rbe("remove", "--yes")
    assert result.returncode != 0
    assert "at least one filter is required" in result.stderr


def test_dry_run_reports_the_plan_without_removing(rbe: CliRun, rows: dict[str, Row]):
    result = rbe(
        "remove",
        "--track-id",
        rows[GAMMA_ONLY].id,
        "--dry-run",
        "--yes",
        "--print",
        "json",
    )
    payload = _load(result)["result"]
    assert payload["dry_run"] is True
    assert [op["id"] for op in payload["removed"]] == [rows[GAMMA_ONLY].id]
    assert GAMMA_ONLY in _titles(rbe)


def test_removes_the_row_and_prints_its_id(rbe: CliRun, rows: dict[str, Row]):
    result = rbe("remove", "--track-id", rows[GAMMA_ONLY].id, "--yes", "--print", "ids")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == rows[GAMMA_ONLY].id
    assert GAMMA_ONLY not in _titles(rbe)


def test_removes_tracks_piped_from_search(rbe: CliRun):
    """search --artist Beta --print ids | remove --yes."""
    ids_result = rbe("search", "--artist", "Beta", "--print", "ids")
    assert ids_result.returncode == 0
    assert len(ids_result.stdout.split()) == 2

    result = rbe("remove", "--yes", stdin=ids_result.stdout)
    assert result.returncode == 0, result.stderr
    assert not [t for t in _titles(rbe) if t.endswith("Beta")]


def test_child_rows_go_with_the_track(
    rbe: CliRun, fresh_db: Path, rows: dict[str, Row]
):
    """Playlist membership, mixer params, and file records are keyed by
    ContentID and reference a row that no longer exists."""
    track_id = rows[GAMMA_ONLY].id
    assert _child_row_count(fresh_db, track_id) > 0

    result = rbe("remove", "--track-id", track_id, "--yes")
    assert result.returncode == 0, result.stderr
    assert _child_row_count(fresh_db, track_id) == 0


def _child_row_count(db_path: Path, track_id: str) -> int:
    """Rows across every mapped table that reference this track."""
    db = Rekordbox6Database(str(db_path))
    assert db.session is not None
    total = 0
    for mapper in tb.Base.registry.mappers:
        cls = mapper.class_
        if cls is tb.DjmdContent or "ContentID" not in cls.__table__.columns:
            continue
        total += (
            db.session.query(cls).filter(cls.__table__.c.ContentID == track_id).count()
        )
    db.close()
    return total


def test_orphaned_artist_and_album_are_collected(
    rbe: CliRun, fresh_db: Path, rows: dict[str, Row]
):
    result = rbe(
        "remove", "--track-id", rows[GAMMA_ONLY].id, "--yes", "--print", "json"
    )
    assert _load(result)["result"]["deleted_relatives"] == 2

    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    assert db.session.query(tb.DjmdArtist).filter_by(Name="Gamma").first() is None
    assert db.session.query(tb.DjmdAlbum).filter_by(Name="AIFF Sampler").first() is None
    db.close()


def test_relatives_another_track_still_holds_survive(
    rbe: CliRun, fresh_db: Path, rows: dict[str, Row]
):
    """Wave Alpha keeps artist Alpha and album Apple Lossless keeps Apple Beta."""
    result = rbe(
        "remove", "--track-id", rows[SHARED_ARTIST].id, "--yes", "--print", "json"
    )
    assert _load(result)["result"]["deleted_relatives"] == 0

    db = Rekordbox6Database(str(fresh_db))
    assert db.session is not None
    assert db.session.query(tb.DjmdArtist).filter_by(Name="Alpha").first() is not None
    assert (
        db.session.query(tb.DjmdAlbum).filter_by(Name="Apple Lossless").first()
        is not None
    )
    db.close()


def test_analysis_directory_is_deleted(
    rbe: CliRun, share_tree: Path, rows: dict[str, Row]
):
    removed, kept = rows[GAMMA_ONLY], rows[SHARED_ARTIST]
    assert removed.analysis_dir is not None and kept.analysis_dir is not None

    result = rbe("remove", "--track-id", removed.id, "--yes")
    assert result.returncode == 0, result.stderr

    assert not removed.analysis_dir.exists()
    # The <xxx> prefix directory held only this track, so it goes too.
    assert not removed.analysis_dir.parent.exists()
    assert (kept.analysis_dir / "ANLZ0000.DAT").is_file()


def test_artwork_files_and_directories_are_deleted(
    rbe: CliRun, share_tree: Path, rows: dict[str, Row]
):
    removed, kept = rows[GAMMA_ONLY], rows[SHARED_ARTIST]
    assert removed.artwork_dir is not None and kept.artwork_dir is not None

    result = rbe("remove", "--track-id", removed.id, "--yes")
    assert result.returncode == 0, result.stderr

    assert not removed.artwork_dir.exists()
    assert not removed.artwork_dir.parent.exists()
    for name in ARTWORK_FILES:
        assert (kept.artwork_dir / name).is_file()


def test_a_track_without_artwork_leaves_the_share_tree_alone(
    rbe: CliRun, fresh_db: Path, share_tree: Path, rows: dict[str, Row]
):
    """An empty ImagePath joins onto the share directory unchanged, so a
    cleanup that trusted it would reach the library's own db directory."""
    removed = rows[NO_ARTWORK]
    assert removed.artwork_dir is None

    result = rbe("remove", "--track-id", removed.id, "--yes")
    assert result.returncode == 0, result.stderr

    assert fresh_db.is_file()
    assert (share_tree / "PIONEER/Artwork").is_dir()
    for title, row in rows.items():
        if title == NO_ARTWORK or row.artwork_dir is None:
            continue
        for name in ARTWORK_FILES:
            assert (row.artwork_dir / name).is_file()


def test_source_audio_is_kept_by_default(rbe: CliRun, rows: dict[str, Row]):
    removed = rows[SOURCE_DELETE]
    result = rbe("remove", "--track-id", removed.id, "--yes", "--print", "json")
    assert _load(result)["result"]["removed"][0]["source_deleted"] is False
    assert removed.source.is_file()


@pytest.mark.usefixtures("restore_staged_audio")
def test_delete_source_removes_the_audio_file(rbe: CliRun, rows: dict[str, Row]):
    removed = rows[SOURCE_DELETE]
    assert removed.source.is_file()

    result = rbe(
        "remove",
        "--track-id",
        removed.id,
        "--delete-source",
        "--yes",
        "--print",
        "json",
    )
    assert _load(result)["result"]["removed"][0]["source_deleted"] is True
    assert not removed.source.exists()
