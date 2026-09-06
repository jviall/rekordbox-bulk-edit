"""Pydantic models for the public API.

Three layers:

- **Filter base** (`FilterArgs`) declares track-selection criteria shared by all
  commands.
- **API/Command request models** (`SearchRequest`, `EditRequest`, `ConvertRequest`, `ImportRequest`, `RemoveRequest`) extend `FilterArgs`
  with command-specific fields, except `ImportRequest`, which selects paths on
  disk rather than existing rows.
- **API/Command response models** (`SearchResponse`, `EditResponse`, `ConvertResponse`, `ImportResponse`, `RemoveResponse`)
  describe what each command returns. `RemoveRequest` and `RemoveResponse` model
  the shape of the `remove()` command.
- **Domain types** (`Track`, `EditOp`, `ConvertOp`, `ImportOp`, `RemoveOp`, `SkippedTrack`)
  which help describe the internals of requests/responses

Response semantics:

- For a write command, `tracks` is what the command actually did: the rows
  it wrote, in their current state. A dry run changes nothing, so `tracks`
  is always empty for a dry run; read `result`'s ops instead to see what was
  planned.
- Tracks the command declined to touch are reached through
  `result.skipped[].track` and are deliberately not mixed into `tracks`.
- `result` summarizes what happened (or would happen in a dry-run). Response
  models should self describe the operation that happened (e.g. the field name
  for edit, the target format for convert) so a response is fully self-describing.
"""

import os
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

# ── Filter base ───────────────────────────────────────────────────────────


class FilterArgs(BaseModel):
    """Track-selection criteria shared by all commands."""

    model_config = ConfigDict(extra="forbid")

    track_id: list[str] = []
    track_ids: list[str] = []
    title: list[str] = []
    exact_title: list[str] = []
    playlist: list[str] = []
    exact_playlist: list[str] = []
    artist: list[str] = []
    exact_artist: list[str] = []
    album: list[str] = []
    exact_album: list[str] = []
    path: list[str] = []
    resolved_path: list[str] = []
    format: list[str] = []
    first: int | None = Field(default=None, gt=0)
    last: int | None = Field(default=None, gt=0)
    match_all: bool = False
    match_any: bool = False

    @model_validator(mode="after")
    def _check_first_last_exclusive(self) -> "FilterArgs":
        if self.first is not None and self.last is not None:
            raise ValueError("'first' and 'last' are mutually exclusive")
        return self

    @model_validator(mode="after")
    def _check_match_mode_exclusive(self) -> "FilterArgs":
        if self.match_all and self.match_any:
            raise ValueError("'match_all' and 'match_any' are mutually exclusive")
        return self


# ── Command args ──────────────────────────────────────────────────────────


class SearchRequest(FilterArgs):
    """Inputs for search(): the shared track filters, with no search-specific fields."""


class EditRequest(FilterArgs):
    """Inputs for edit(): the shared track filters plus the field to change and its new value."""

    field: str
    replace_value: str
    match_pattern: str | None = None
    allow_missing: bool = False
    """Write a FolderPath that does not exist, rather than skipping the track.
    The audio columns describing the file are left as they are, since there is
    no file to read them from."""
    allow_mismatch: bool = False
    """Write a FolderPath whose duration contradicts the track's stored length,
    rather than skipping the track. Cues and the beat grid are time-indexed
    against the old duration, so they may land misaligned."""


DeleteOriginalsMode: TypeAlias = Literal["none", "lossless", "all"]

#: Concurrent encodes when the caller does not choose. See ConvertRequest.threads.
DEFAULT_THREADS = min(4, os.cpu_count() or 1)


class ConvertRequest(FilterArgs):
    """Inputs for convert(): the shared track filters plus output format and original-file handling."""

    format_out: str
    """The target format. Required: a conversion that picked its own output
    format would be a guess at what the caller wanted."""
    delete_originals: DeleteOriginalsMode = "none"
    """When to delete original files after conversion: "none" (the default)
    never deletes them, "all" always deletes them, and "lossless" deletes them
    only when the conversion loses no audio information. Down-sampling to the
    conversion target counts as lossy, as does MP3 output."""
    overwrite: bool = False
    threads: int = Field(default_factory=lambda: DEFAULT_THREADS, ge=1)
    """How many files to encode concurrently."""


class ImportRequest(BaseModel):
    """Inputs for import_tracks(): files or directories, and where to put them.

    Unlike the other commands, this does not extend FilterArgs: its input is
    paths on disk whose rows do not exist yet.
    """

    model_config = ConfigDict(extra="forbid")

    paths: list[str] = []
    playlist: str | None = None
    recurse: bool = False
    """Authorize walking directory arguments recursively. The CLI sets this
    from --yes, and from an answered walk prompt."""


class RemoveRequest(FilterArgs):
    """Inputs for remove(): which tracks to delete, and whether to unlink their
    source audio files as well."""

    delete_source: bool = False


# ── Domain types ──────────────────────────────────────────────────────────


class Track(BaseModel):
    """A Rekordbox track.
    Field names mirror the [DjmdContent](https://pyrekordbox.readthedocs.io/en/latest/formats/db6.html#djmdcontent)
    table's column names, except where additional derived fields have been added for convenience.
    What's defined here are just the fields RBE cares about, but all database columns and their raw
    are silently included in each Track instance, and are included in `--print json`.
    """

    model_config = ConfigDict(extra="allow")

    AlbumName: str | None = None
    Analysed: int | None = None
    AnalysisUpdated: str | None = None
    ArtistName: str | None = None
    BitDepth: int | None = None
    BitRate: int | None = None
    Commnt: str | None = None
    DateCreated: str | None = None
    FileNameL: str
    FileNameS: str | None = None
    FileType: int | None = None
    FolderPath: str
    ID: str
    Length: int | None = None
    Rating: int | None = None
    ReleaseDate: str | None = None
    ReleaseYear: int | None = None
    SampleRate: int | None = None
    Tag: str | None = None
    Title: str | None = None
    TrackNo: int | None = None


SkipReason: TypeAlias = Literal[
    "no_change",
    "already_target_format",
    "unsupported_source_format",
    "output_file_exists",
    "codec_mismatch",
    "file_not_found",
    "length_mismatch",
    "unknown_file_type",
    "already_exists",
    "unsupported_file_type",
    "unreadable_file",
    # Approved during the preview, then its file or its database row changed
    # before the write ran.
    "db_or_fs_changed",
]


class SkippedTrack(BaseModel):
    """A track the command declined to operate on, and the row it declined to
    touch. e.g. A result in a [convert][rekordbox_edit.api.convert] command that
    is already the target format.
    """

    reason: SkipReason
    track: Track | None = None
    """The track the command passed over, in its state at that point.

    None only where there is no track to describe: an import rejecting a file
    type it does not recognize, or one whose tags it could not read, has
    neither a database record nor usable tags.
    """


class EditOp(BaseModel):
    """A planned or performed edit: track ID + the value it would / did become."""

    id: str
    new_value: str
    track: Track
    """The track this edit acted on: its state before the write during a dry
    run, or as written once the edit is applied."""


class ConvertOp(BaseModel):
    """A planned or performed conversion: track ID, source/output paths, and
    the file type, bit depth, and sample rate on each side. Source audio
    fields mirror the database record; output fields reflect the conversion
    target, with the sample rate clamped to the source so a conversion never
    up-samples. `track` is the track it acts on."""

    id: str
    source_path: str
    output_path: str
    source_file_type: str | None = None
    source_bit_depth: int | None = None
    source_sample_rate: int | None = None
    output_file_type: str | None = None
    output_bit_depth: int | None = None
    output_sample_rate: int | None = None
    track: Track
    """The track this conversion acted on: its state before conversion during
    a dry run, or as written once the conversion is applied."""


class ImportOp(BaseModel):
    """A planned or performed import. `action` distinguishes a newly created row
    from a track that already existed and was only added to a playlist. `id` is
    empty for a planned create, which has no ID until the row is inserted."""

    id: str
    path: str
    action: Literal["create", "playlist_add"]
    track: Track
    """The track this op describes: the planned row's synthetic data for a
    create still awaiting insertion, the existing row for a playlist add, or
    the newly written row once a create is applied."""


class RemoveOp(BaseModel):
    """A planned or performed removal. `track` is the row as it stood
    immediately before deletion, since it cannot be read afterward.
    `source_deleted` is False for a planned removal, for a run without
    --delete-source, and for a source file that was already gone."""

    id: str
    track: Track
    source_deleted: bool = False


# ── Response envelopes ────────────────────────────────────────────────────


class SearchResponse(BaseModel):
    tracks: list[Track]


class EditResult(BaseModel):
    """Result payload for edit()."""

    field: str
    dry_run: bool
    edits: list[EditOp]
    skipped: list[SkippedTrack]


class EditResponse(BaseModel):
    result: EditResult

    @computed_field
    @property
    def tracks(self) -> list[Track]:
        """The rows this edit wrote, in their current state. Empty for a dry
        run, since a dry run changes nothing; see `result.edits` for what was
        planned."""
        if self.result.dry_run:
            return []
        return [op.track for op in self.result.edits]


class ConvertResult(BaseModel):
    """Result payload for convert()."""

    format_out: str
    dry_run: bool
    converted: list[ConvertOp]
    deleted: int
    skipped: list[SkippedTrack]


class ConvertResponse(BaseModel):
    result: ConvertResult

    @computed_field
    @property
    def tracks(self) -> list[Track]:
        """The rows this conversion wrote, in their current state. Empty for a
        dry run, since a dry run changes nothing; see `result.converted` for
        what was planned."""
        if self.result.dry_run:
            return []
        return [op.track for op in self.result.converted]


class ImportResult(BaseModel):
    """Result payload for import_tracks()."""

    playlist: str | None
    dry_run: bool
    added: list[ImportOp]
    skipped: list[SkippedTrack]


class ImportResponse(BaseModel):
    result: ImportResult

    @computed_field
    @property
    def tracks(self) -> list[Track]:
        """The rows this import created or added to the playlist, in their
        current state. Empty for a dry run, since a dry run changes nothing;
        see `result.added` for what was planned."""
        if self.result.dry_run:
            return []
        return [op.track for op in self.result.added]


class RemoveResult(BaseModel):
    """Result payload for remove().

    `deleted_relatives` counts the shared artist, album, genre, and label
    records the removal left behind and deleted. It is an aggregate rather
    than a per-op field because such a record is not attributable to one
    track.
    """

    dry_run: bool
    removed: list[RemoveOp]
    skipped: list[SkippedTrack]
    deleted_relatives: int


class RemoveResponse(BaseModel):
    result: RemoveResult

    @computed_field
    @property
    def tracks(self) -> list[Track]:
        """The rows this command removed, as they stood before deletion.
        Empty for a dry run, since a dry run changes nothing; see
        `result.removed` for what was planned."""
        if self.result.dry_run:
            return []
        return [op.track for op in self.result.removed]
