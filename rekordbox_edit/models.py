"""Pydantic models for the public API.

Three layers:

- **Filter base** (`FilterArgs`) declares track-selection criteria shared by all
  commands.
- **API/Command request models** (`SearchRequest`, `EditRequest`, `ConvertRequest`) extend `FilterArgs`
  with command-specific fields.
- **API/Command response models** (`SearchResponse`, `EditResponse`, `ConvertResponse`)
  describe what each command returns.
- **Domain types** (`Track`, `EditOp`, `ConvertOp`, `SkippedTrack`)
  which help describe the internals of requests/responses

Response semantics:

- `tracks` always reflects the **current DB state** at the moment the response
  was built. Pre-execute for dry-runs, post-execute for write runs.
- `result` summarizes what happened (or would happen in a dry-run). Response
  models should self describe the operation that happened (e.g. the field name
  for edit, the target format for convert) so a response is fully self-describing.
- `tracks` and `result.edits` / `result.converted` align 1:1 in their contents and
  order by index;
"""

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    exact_path: list[str] = []
    format: list[str] = []
    first: int | None = Field(default=None, gt=0)
    last: int | None = Field(default=None, gt=0)
    match_all: bool = False

    @model_validator(mode="after")
    def _check_first_last_exclusive(self) -> "FilterArgs":
        if self.first is not None and self.last is not None:
            raise ValueError("'first' and 'last' are mutually exclusive")
        return self


# ── Command args ──────────────────────────────────────────────────────────


class SearchRequest(FilterArgs):
    """Inputs for search(): the shared track filters, with no search-specific fields."""


class EditRequest(FilterArgs):
    """Inputs for edit(): the shared track filters plus the field to change and its new value."""

    field: str
    replace_value: str
    match_pattern: str | None = None
    multi: bool = False


DeleteOriginalsMode: TypeAlias = Literal["none", "lossless", "all"]


class ConvertRequest(FilterArgs):
    """Inputs for convert(): the shared track filters plus output format and original-file handling."""

    format_out: str = "aiff"
    delete_originals: DeleteOriginalsMode = "lossless"
    """When to delete original files after conversion: "all" always deletes
    them, "none" never deletes them, and "lossless" (the default) deletes them
    only when the conversion loses no audio information. Down-sampling to the
    conversion target counts as lossy, as does MP3 output."""
    overwrite: bool = False


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
]


class SkippedTrack(BaseModel):
    """A track the command declined to operate on.
    e.g. A result in a [convert][rekordbox_edit.api.convert] command that is already the target format.
    """

    id: str
    reason: SkipReason


class EditOp(BaseModel):
    """A planned or performed edit: track ID + the value it would / did become."""

    id: str
    new_value: str


class ConvertOp(BaseModel):
    """A planned or performed conversion: track ID, source/output paths, and
    the file type, bit depth, and sample rate on each side. Source audio
    fields mirror the database record; output fields reflect the conversion
    target, with the sample rate clamped to the source so a conversion never
    up-samples."""

    id: str
    source_path: str
    output_path: str
    source_file_type: str | None = None
    source_bit_depth: int | None = None
    source_sample_rate: int | None = None
    output_file_type: str | None = None
    output_bit_depth: int | None = None
    output_sample_rate: int | None = None


# ── Response envelopes ────────────────────────────────────────────────────


class SearchResponse(BaseModel):
    tracks: list[Track]


class EditResult(BaseModel):
    """Result payload for edit(). `edits` aligns 1:1 with response.tracks."""

    field: str
    edits: list[EditOp]
    skipped: list[SkippedTrack]


class EditResponse(BaseModel):
    tracks: list[Track]
    result: EditResult

    @model_validator(mode="after")
    def _check_edit_alignment(self) -> "EditResponse":
        if len(self.tracks) != len(self.result.edits):
            raise ValueError(
                f"tracks ({len(self.tracks)}) and result.edits "
                f"({len(self.result.edits)}) must align 1:1"
            )
        return self


class ConvertResult(BaseModel):
    """Result payload for convert(). `converted` aligns 1:1 with response.tracks."""

    format_out: str
    converted: list[ConvertOp]
    deleted: int
    skipped: list[SkippedTrack]


class ConvertResponse(BaseModel):
    tracks: list[Track]
    result: ConvertResult

    @model_validator(mode="after")
    def _check_convert_alignment(self) -> "ConvertResponse":
        if len(self.tracks) != len(self.result.converted):
            raise ValueError(
                f"tracks ({len(self.tracks)}) and result.converted "
                f"({len(self.result.converted)}) must align 1:1"
            )
        return self
