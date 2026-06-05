"""Pydantic models for CLI argument groups.

Two layers:

- **Component models** (`FilterArgs`, `ConfirmationArgs`, `EditArgs`,
  `ConvertArgs`) declare cohesive subsets of inputs. Each is the typed object
  consumed by a narrow internal helper — most notably `FilterArgs` →
  `get_filtered_content`.
- **Command models** (`EditCommandArgs`, `ConvertCommandArgs`) compose the
  components via model inheritance, producing a flat shape with every field
  the corresponding command needs. The private `_edit` / `_convert` helpers
  accept exactly one command model.

A caller can construct either form via kwargs or `model_validate({...})`:

    _edit(EditCommandArgs(field="Title", replace_value="X", artist=["Y"]))
    _edit(EditCommandArgs.model_validate(config_dict))
"""

from pydantic import BaseModel, ConfigDict

from rekordbox_edit._click import PrintChoice


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

    `field` names a column from `FIELD_COLUMNS` in `commands/edit.py`.
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
    `_convert`, while `True` / `False` are explicit.
    """

    model_config = ConfigDict(extra="forbid")

    format_out: str = "aiff"
    delete: bool | None = None
    overwrite: bool = False


class SearchCommandArgs(FilterArgs):
    """All inputs `_search` accepts. Search is a read-only command, so it
    inherits only the filter group and adds `print_opt`.
    """

    print_opt: PrintChoice | None = None


class EditCommandArgs(FilterArgs, ConfirmationArgs, EditArgs):
    """All inputs `_edit` accepts, composed from the three component groups.

    Inherits via Pydantic model inheritance: every field of every parent
    appears flat in this model. Liskov also holds, so an `EditCommandArgs`
    can be passed anywhere a `FilterArgs`/`ConfirmationArgs`/`EditArgs` is
    expected (e.g. `get_filtered_content(db, args)`).
    """

    print_opt: PrintChoice | None = None


class ConvertCommandArgs(FilterArgs, ConfirmationArgs, ConvertArgs):
    """All inputs `_convert` accepts, composed from the three component groups."""

    print_opt: PrintChoice | None = None
