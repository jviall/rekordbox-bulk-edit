"""Pydantic models for CLI argument groups.

These types are the public API of the functional layer below the CLI: callers
of `get_filtered_content` and the private command helpers receive them in lieu
of long flat parameter lists. Each `*_from_kwargs` factory packs the matching
Click parameters into its model.
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


def filter_args_from_kwargs(**kwargs) -> FilterArgs:
    """Pack the flat Click kwargs for the `global_click_filters` group into a FilterArgs."""
    return FilterArgs(
        **{
            k: v
            for k, v in kwargs.items()
            if k in FilterArgs.model_fields and v is not None
        }
    )


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


def confirmation_args_from_kwargs(**kwargs) -> ConfirmationArgs:
    """Pack the flat Click kwargs for the `global_click_confirmations` group into a ConfirmationArgs."""
    return ConfirmationArgs(
        **{
            k: v
            for k, v in kwargs.items()
            if k in ConfirmationArgs.model_fields and v is not None
        }
    )


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


def edit_args_from_kwargs(**kwargs) -> EditArgs:
    """Pack the flat Click kwargs for the `edit_click_options` group plus `field` into an EditArgs."""
    return EditArgs(**{k: v for k, v in kwargs.items() if k in EditArgs.model_fields})


class ConvertArgs(BaseModel):
    """Convert-command inputs that describe the output and conflict policy.

    `delete` is tri-state: `None` defers to a per-format default in
    `_convert`, while `True` / `False` are explicit.
    """

    model_config = ConfigDict(extra="forbid")

    format_out: str
    delete: bool | None = None
    overwrite: bool = False


def convert_args_from_kwargs(**kwargs) -> ConvertArgs:
    """Pack the flat Click kwargs for the `convert_click_options` group into a ConvertArgs."""
    return ConvertArgs(
        **{k: v for k, v in kwargs.items() if k in ConvertArgs.model_fields}
    )
