"""Pydantic models for the public API and CLI argument groups.

Four layers:

- **Component models** (`FilterArgs`, `ConfirmationArgs`, `EditArgs`,
  `ConvertArgs`) declare cohesive subsets of inputs.
- **API contract types** (`EditPlanArgs`, `ConvertPlanArgs`) compose
  component models into the typed inputs that `plan_edit` and `plan_convert`
  accept. They contain no CLI-specific fields.
- **Command models** (`EditCommandArgs`, `ConvertCommandArgs`) extend the
  API types with `ConfirmationArgs` for CLI use.
- **Domain model** (`Track`) is the sole return type of the API layer.
  Field names mirror DjmdContent column names so conversion is mechanical.
"""

from pydantic import BaseModel, ConfigDict


class FilterArgs(BaseModel):
    """Filter inputs forwarded to `get_filtered_content`.

    Field names mirror the Click parameter names: `track_ids` holds the
    positional TRACK_IDS argument (variadic), `track_id` holds the values of
    the repeated `--track-id` option.
    """

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
    match_all: bool = False


class ConfirmationArgs(BaseModel):
    """How the user gates a side effect before it lands.

    `dry_run` skips the change entirely. `yes` skips confirmation and applies
    the batch. `interactive` prompts per item. With all three false, the
    caller is expected to prompt once for the batch.
    """

    model_config = ConfigDict(extra="forbid")

    dry_run: bool = False
    yes: bool = False
    interactive: bool = False


class EditArgs(BaseModel):
    """Edit-command inputs that describe what to change.

    `field` names a column from `FIELD_COLUMNS` in `api/edit.py`.
    `match_pattern` is the optional substring to find within the current value;
    when omitted, the whole value is replaced. `multi` allows the edit to
    apply to more than one matched track.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    replace_value: str
    match_pattern: str | None = None
    multi: bool = False


class ConvertArgs(BaseModel):
    """Convert-command inputs that describe the output and conflict policy.

    `delete` is tri-state: `None` defers to a per-format default in
    `plan_convert`, while `True` / `False` are explicit.
    """

    model_config = ConfigDict(extra="forbid")

    format_out: str = "aiff"
    delete: bool | None = None
    overwrite: bool = False


class Track(BaseModel):
    """Domain model for a Rekordbox track.

    Field names mirror DjmdContent column names so conversion is a mechanical
    field copy with no translation. This type is the sole return type of the
    API layer — ORM objects never cross the API boundary.

    `extra="allow"` lets `_track_from_content` bulk-copy every DjmdContent
    column without enumerating each one; the declared fields below stay typed
    and validated, undeclared columns ride along as untyped attributes.
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


class EditPlanArgs(FilterArgs, EditArgs):
    """Inputs for `plan_edit`: filter criteria plus edit specification."""


class ConvertPlanArgs(FilterArgs, ConvertArgs):
    """Inputs for `plan_convert`: filter criteria plus conversion specification."""


class EditCommandArgs(EditPlanArgs, ConfirmationArgs):
    """All inputs the edit CLI command accepts.

    Inherits via Pydantic model inheritance: every field of every parent
    appears flat in this model. An `EditCommandArgs` can be passed anywhere
    an `EditPlanArgs` or `FilterArgs` is expected.
    """


class ConvertCommandArgs(ConvertPlanArgs, ConfirmationArgs):
    """All inputs the convert CLI command accepts."""
