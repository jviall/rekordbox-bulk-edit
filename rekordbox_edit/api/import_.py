"""Import API for rekordbox-edit."""

import datetime
import logging
import os
from dataclasses import dataclass
from typing import NamedTuple, cast

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb

from rekordbox_edit.api._utils import stamp_usns, track_from_content, writing
from rekordbox_edit.errors import InputError
from rekordbox_edit.models import (
    ImportOp,
    ImportRequest,
    ImportResponse,
    ImportResult,
    SkippedTrack,
    Track,
)
from rekordbox_edit.query import (
    find_content_by_key,
    find_playlists_by_name,
    normalize_path,
    require_session,
)
from rekordbox_edit.tags import TrackTags, UnreadableFile, read_tags
from rekordbox_edit.utils import FILE_TYPES

logger = logging.getLogger(__name__)

# Every extension RBE recognizes, and the subset add_content cannot type.
# add_content resolves the file type with `getattr(FileType, suffix)`, which
# raises AttributeError (not the ValueError its handler catches) for a suffix
# pyrekordbox's FileType enum has no member for. Those extensions are still
# collected so one is reported as skipped rather than passing silently, and
# VIDEO declares no extensions at all, so a video container is never collected.
AUDIO_EXTENSIONS = frozenset(
    extension for info in FILE_TYPES.items() for extension in info.extensions
)
UNMAPPED_EXTENSIONS = frozenset(
    extension
    for extension in AUDIO_EXTENSIONS
    if extension.lstrip(".").upper() not in tb.FileType.__members__
)


class ImportInputError(InputError):
    """The request itself is invalid: a path that does not exist, an
    unconfirmed directory argument, or a playlist name that matches no
    playlist or more than one. Distinct from a write-phase failure, which
    means the database failed and must not be reported as user error."""


class DirectoryConfirmationRequired(ImportInputError):
    """Directory arguments would be walked recursively without `recurse` set.

    Carries the counts so a caller can compose its own prompt, and its own
    hint about whatever it calls the authorization, rather than parsing
    either back out of the message.
    """

    def __init__(self, directories: int, files: int):
        self.directories = directories
        self.files = files
        super().__init__(
            f"{directories} directory argument(s) would be walked recursively, "
            f"adding {files} file(s)."
        )


@dataclass
class _ImportCandidate:
    """One file under consideration, with its resolved forms computed once.

    normalize_path() calls Path.resolve(), which touches the filesystem, so
    every later phase reads `stored` and `key` off the candidate instead of
    re-deriving them. `key` is the case-folded form find_content_by_key
    matches against, folded because Rekordbox's stored case can differ from
    the live filesystem's and Path.resolve() does not correct case on macOS.
    `tags` is filled by _classify_import for create ops only.
    """

    path: str
    stored: str
    key: str
    tags: TrackTags | None = None

    @classmethod
    def of(cls, path: str) -> "_ImportCandidate":
        stored = normalize_path(path)
        return cls(path=path, stored=stored, key=stored.casefold())


class _Expansion(NamedTuple):
    candidates: list[_ImportCandidate]
    directories: list[str]
    rejected: list[str]


def _is_audio(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in AUDIO_EXTENSIONS


def _expand_paths(paths: list[str]) -> _Expansion:
    """Resolve arguments to a de-duplicated, sorted list of candidates.

    Both a named file and a walked directory are filtered to AUDIO_EXTENSIONS.
    De-duplication is by match key, so two spellings of one file (an absolute
    and a relative path, say) collapse into a single candidate: both would
    classify as "create" and the second db.add_content call would raise. The
    walked directories and the rejected named files come back too, so the
    caller can gate on the former and report the latter.
    """
    found: list[str] = []
    directories: list[str] = []
    rejected: list[str] = []
    for raw in paths:
        if os.path.isfile(raw):
            (found if _is_audio(raw) else rejected).append(raw)
        elif os.path.isdir(raw):
            directories.append(raw)
            for root, _, names in os.walk(raw):
                found.extend(
                    os.path.join(root, name) for name in names if _is_audio(name)
                )
        else:
            raise ImportInputError(f"Path does not exist: {raw}")

    candidates: dict[str, _ImportCandidate] = {}
    for path in sorted(found):
        candidate = _ImportCandidate.of(path)
        candidates.setdefault(candidate.key, candidate)

    logger.debug(
        f"expanded {len(paths)} argument(s) to {len(candidates)} file(s), "
        f"{len(directories)} directory walk(s), {len(rejected)} rejected"
    )
    return _Expansion(
        list(candidates.values()), directories, sorted(dict.fromkeys(rejected))
    )


# Columns Rekordbox writes as an empty value where add_content leaves NULL,
# plus the columns analysis owns, which are set to zero.
# HotCueAutoLoad is deliberately absent: add_content already passes it positionally
# into DjmdContent.create() ahead of **kwargs, so repeating it here raises
# "got multiple values for keyword argument 'HotCueAutoLoad'". The value
# add_content writes ("on") already matches Rekordbox's own imports.
IMPORT_DEFAULTS: dict[str, object] = {
    "FileNameS": "",
    "OrgFolderPath": "",
    "ImagePath": "",
    "Subtitle": "",
    "ReleaseDate": "",
    "ModifiedByRBM": "",
    "DeliveryComment": "",
    "Lyricist": "",
    "Reserved1": "",
    "ColorID": "0",
    "VideoAssociate": "0",
    "ExtInfo": "null",
    "DeliveryControl": "on",
    "AnalysisDataPath": "",
    "Rating": 0,
    "DJPlayCount": 0,
    "LyricStatus": 0,
    "SamplerTrackInfo": 0,
    "SamplerPlayOffset": 0,
    "ServiceID": 0,
    "SamplerGain": 0.0,
    "rb_data_status": 0,
    "rb_local_data_status": 0,
    "rb_local_deleted": 0,
    "rb_local_synced": 0,
    # Analysis fills these; an import leaves them zero.
    "SampleRate": 0,
    "BitRate": 0,
    "BitDepth": 0,
    "BPM": 0,
    "Analysed": 0,
}


def _get_or_create(db, table, name: str, factory, created: list | None = None):
    """Reuse a row matching by name, else create one.

    Same query shape as RelationalField._get_or_create in api/field_handlers.py,
    generalized over a table and factory so one function covers all five
    relational columns instead of a per-kind branch.

    New rows are appended to `created` when given: add_content flushes,
    which moves them out of session.new before they can be found again.
    """
    existing = db.session.query(table).filter_by(Name=name).order_by(table.ID).first()
    if existing is not None:
        return existing
    row = factory(name)
    if created is not None:
        created.append(row)
    return row


def _resolve_relations(
    db: Rekordbox6Database, tags: TrackTags, created: list | None = None
) -> dict[str, str]:
    """Foreign keys for a track's tags, creating shared rows as needed.

    A tag that is absent yields no key, leaving the column at add_content's
    default. KeyID is the exception: DjmdKey is a fixed table with no add_key
    helper, so an unmatched key falls back to Rekordbox's '0' sentinel.
    """
    session = require_session(db)
    relations: dict[str, str] = {}
    for field, column, table, factory in (
        ("artist", "ArtistID", tb.DjmdArtist, db.add_artist),
        ("composer", "ComposerID", tb.DjmdArtist, db.add_artist),
        ("album", "AlbumID", tb.DjmdAlbum, db.add_album),
        ("genre", "GenreID", tb.DjmdGenre, db.add_genre),
        ("label", "LabelID", tb.DjmdLabel, db.add_label),
    ):
        value = tags.get(field)
        if value:
            relations[column] = _get_or_create(db, table, value, factory, created).ID

    key = tags.get("key")
    row = (
        session.query(tb.DjmdKey)
        .filter_by(ScaleName=key)
        .order_by(tb.DjmdKey.ID)
        .first()
        if key
        else None
    )
    relations["KeyID"] = row.ID if row else "0"
    return relations


def _created_date(path: str) -> str:
    """The file's creation date, as Rekordbox records DateCreated.

    st_birthtime is macOS and BSD only; Windows reports creation time as
    st_ctime, and elsewhere mtime is the closest available value.
    """
    stat = os.stat(path)
    stamp = getattr(stat, "st_birthtime", None)
    if stamp is None:
        stamp = stat.st_ctime if os.name == "nt" else stat.st_mtime
    return datetime.date.fromtimestamp(stamp).isoformat()


def _build_content(
    db: Rekordbox6Database, candidate: _ImportCandidate, created: list | None = None
):
    """Create the DjmdContent row for one file and return it.

    add_content supplies the identity and device columns. Three of its values
    are corrected afterward rather than passed as kwargs: it writes them
    positionally into DjmdContent.create() ahead of **kwargs, so passing them
    raises TypeError.
    """
    tags = cast(TrackTags, candidate.tags)
    content = db.add_content(
        candidate.stored,
        **IMPORT_DEFAULTS,
        **_resolve_relations(db, tags, created),
        Title=tags["title"],
        Commnt=tags["comment"] or "",
        ISRC=tags["isrc"] or "",
        TrackNo=tags["track_no"] or 0,
        DiscNo=tags["disc_no"] or 0,
        ReleaseYear=tags["release_year"] or 0,
        Length=tags["length"] or 0,
    )
    # add_content types by extension, mapping every .m4a to AAC, and stamps
    # DateCreated with today rather than the file's own date.
    if tags["file_type"] is not None:
        content.FileType = tags["file_type"]
    content.DateCreated = _created_date(candidate.path)
    # add_content stores str(Path(path)), which is backslashed on Windows.
    # Rekordbox forward-slashes FolderPath on every platform.
    content.FolderPath = candidate.stored
    logger.debug(f"built content row for {candidate.stored} type={content.FileType}")
    return content


def _classify_import(
    candidate: _ImportCandidate,
    existing: "tb.DjmdContent | None",
    playlist_member_ids: set[str],
    playlist: "tb.DjmdPlaylist | None",
) -> ImportOp | SkippedTrack:
    """Decide what should happen to one candidate file.

    A track already in the library is not re-added, but it is placed in the
    requested playlist when it is missing from it. `playlist` is the resolved
    row (or None), never the raw request field, so this always agrees with
    whatever the write phase does with the same value. A new track has to
    clear two more gates before it counts as a create: a file type
    add_content can store, and tags mutagen can read. Its tags are recorded
    on the candidate for the write phase.
    """
    path = candidate.path
    if existing is not None:
        content_id = str(existing.ID)
        track = track_from_content(existing)
        if playlist is not None and content_id not in playlist_member_ids:
            logger.debug(f"playlist_add id={content_id} path={path}")
            return ImportOp(
                id=content_id, path=path, action="playlist_add", track=track
            )
        logger.debug(f"skip import id={content_id} reason=already_exists path={path}")
        return SkippedTrack(reason="already_exists", track=track)

    if os.path.splitext(path)[1].lower() in UNMAPPED_EXTENSIONS:
        logger.warning(f"Skipping {path}: unsupported file type")
        return SkippedTrack(reason="unsupported_file_type")

    try:
        candidate.tags = read_tags(path)
    except UnreadableFile as e:
        logger.warning(f"Skipping {path}: {e}")
        return SkippedTrack(reason="unreadable_file")

    return ImportOp(id="", path=path, action="create", track=_planned_track(candidate))


def _resolve_playlist(db: Rekordbox6Database, name: str) -> tb.DjmdPlaylist:
    """The single playlist matching `name`. Raises ImportInputError otherwise."""
    matches = find_playlists_by_name(db, name)
    if not matches:
        raise ImportInputError(f"No playlist named {name!r}.")
    if len(matches) > 1:
        ids = ", ".join(str(p.ID) for p in matches)
        raise ImportInputError(f"{len(matches)} playlists named {name!r} (IDs {ids}).")
    return matches[0]


def _planned_track(candidate: _ImportCandidate) -> Track:
    """A Track describing a row that does not exist yet, for dry-run output.

    ID is empty because the row has no ID until it is inserted.
    """
    tags = cast(TrackTags, candidate.tags)
    return Track(
        ID="",
        FolderPath=candidate.stored,
        FileNameL=candidate.stored.rsplit("/", 1)[-1],
        Title=tags["title"],
        ArtistName=tags["artist"],
        AlbumName=tags["album"],
        FileType=tags["file_type"],
        Length=tags["length"],
    )


def _response(
    playlist_name: str | None,
    ops: list[ImportOp],
    skipped: list[SkippedTrack],
    *,
    dry_run: bool,
) -> ImportResponse:
    return ImportResponse(
        result=ImportResult(
            playlist=playlist_name, dry_run=dry_run, added=ops, skipped=skipped
        ),
    )


def import_tracks(
    db: Rekordbox6Database,
    args: ImportRequest,
    *,
    dry_run: bool = False,
    ops: list[ImportOp] | None = None,
) -> ImportResponse:
    """Create database rows for audio files Rekordbox does not yet know about.

    With `dry_run=True`, returns the planned adds without any DB writes.

    Pass `ops` to import an already-approved plan. The requested directories
    are not walked again, so a file created since the plan was made cannot be
    imported unpreviewed; an op whose file is gone is reported as
    `db_or_fs_changed`.
    """
    logger.debug(f"import start paths={len(args.paths)} dry_run={dry_run}")

    skipped: list[SkippedTrack] = []
    if ops is None:
        candidates, directories, rejected = _expand_paths(args.paths)
        if directories and not args.recurse:
            raise DirectoryConfirmationRequired(len(directories), len(candidates))
        for path in rejected:
            logger.warning(f"Skipping {path}: not an audio file RBE recognizes")
            skipped.append(SkippedTrack(reason="unsupported_file_type"))
    else:
        candidates = []
        for op in ops:
            if not os.path.exists(op.path):
                logger.debug(f"skip import reason=db_or_fs_changed path={op.path}")
                skipped.append(SkippedTrack(reason="db_or_fs_changed", track=op.track))
                continue
            candidates.append(_ImportCandidate.of(op.path))

    session = require_session(db)

    playlist = _resolve_playlist(db, args.playlist) if args.playlist else None
    member_ids: set[str] = set()
    if playlist is not None:
        member_ids = {
            str(song.ContentID)
            for song in session.query(tb.DjmdSongPlaylist).filter_by(
                PlaylistID=playlist.ID
            )
        }

    existing = find_content_by_key(db, [c.key for c in candidates])

    # Paired so the write and dry-run phases reach a candidate's resolved path
    # and tags without looking either up again by string.
    planned: list[tuple[ImportOp, _ImportCandidate]] = []
    for candidate in candidates:
        result = _classify_import(
            candidate, existing.get(candidate.key), member_ids, playlist
        )
        if isinstance(result, SkippedTrack):
            skipped.append(result)
        else:
            planned.append((result, candidate))
    ops = [op for op, _ in planned]
    logger.debug(f"import classified ops={len(ops)} skipped={len(skipped)}")

    if dry_run:
        return _response(args.playlist, ops, skipped, dry_run=True)

    applied: list[ImportOp] = []
    written: list[tb.DjmdContent] = []
    with writing(db, "import"):
        try:
            # Relational rows created along the way each take a USN too.
            incidental: list = []
            for op, candidate in planned:
                if op.action == "create":
                    content = _build_content(db, candidate, incidental)
                    applied.append(op.model_copy(update={"id": str(content.ID)}))
                else:
                    content = existing[candidate.key]
                    applied.append(op)
                written.append(content)
                if playlist is not None:
                    db.add_to_playlist(playlist, content)

            stamp_usns(db, [*written, *incidental])
            session.commit()
            logger.debug(f"import committed {len(applied)} row(s)")
        except BaseException:
            logger.error(
                f"import rolling back after {len(applied)} partial operation(s)"
            )
            session.rollback()
            raise

    # Refreshed post-commit: a create op's track up to now is _planned_track's
    # synthetic, ID-less stand-in, and the row's ID and stamped USN are only
    # settled once the transaction above commits.
    applied = [
        op.model_copy(update={"track": track_from_content(content)})
        for op, content in zip(applied, written)
    ]
    return _response(args.playlist, applied, skipped, dry_run=False)
