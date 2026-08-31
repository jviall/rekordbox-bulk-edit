from enum import Enum
from pathlib import Path

import click

from rekordbox_edit.models import DEFAULT_THREADS


class PrintChoice(Enum):
    SILENT = 0
    IDS = 1
    INFO = 2
    DEBUG = 3
    JSON = 4


print_option = click.option(
    "--print",
    "print_opt",  # avoid shadowing the print() function
    default="info",
    type=click.Choice(PrintChoice, case_sensitive=False),
    help="Configures the kind of console output you want from the command, if any. Use 'ids' to pipe a list of resulting content IDs or 'json' to pipe full track records into another command.",
)

track_ids_argument = click.argument("track-ids", type=str, required=False, nargs=-1)

global_click_filters = [
    click.option(
        "--track-id",
        type=str,
        multiple=True,
        help="Filter by the given Database Track ID",
    ),
    click.option(
        "--title",
        type=str,
        multiple=True,
        help="Find track names that include this value",
    ),
    click.option(
        "--exact-title",
        type=str,
        multiple=True,
        help="Find track names that are exactly this value",
    ),
    click.option(
        "--playlist",
        type=str,
        multiple=True,
        help="Find tracks in playlists whose names include this value",
    ),
    click.option(
        "--exact-playlist",
        type=str,
        multiple=True,
        help="Find tracks in the plalist whose name is exactly this value",
    ),
    click.option(
        "--artist",
        type=str,
        multiple=True,
        help="Find tracks whose Artist names include this value",
    ),
    click.option(
        "--exact-artist",
        type=str,
        multiple=True,
        help="Find tracks whose Artists names are exactly this value",
    ),
    click.option(
        "--album",
        type=str,
        multiple=True,
        help="Find tracks whose Album names include this value",
    ),
    click.option(
        "--exact-album",
        type=str,
        multiple=True,
        help="Find tracks whose Album names are exactly this value",
    ),
    click.option(
        "--path",
        type=str,
        multiple=True,
        help="Find tracks whose file paths contain this value (case-insensitive)",
    ),
    click.option(
        "--resolved-path",
        type=str,
        multiple=True,
        help="Find tracks whose file paths contain this value after it is "
        "resolved to an absolute path (case-insensitive)",
    ),
    click.option(
        "--format",
        type=click.Choice(
            ["mp3", "mp4", "aac", "flac", "alac", "wav", "aiff", "video", "invalid"],
            case_sensitive=False,
        ),
        multiple=True,
        help="Find tracks of this format",
    ),
    click.option(
        "--first",
        type=click.IntRange(min=1),
        default=None,
        help="Return only the first N results",
    ),
    click.option(
        "--last",
        type=click.IntRange(min=1),
        default=None,
        help="Return only the last N results",
    ),
    click.option(
        "--match-all",
        type=bool,
        is_flag=True,
        help="Flatten every filter value, including repeats, into one AND",
    ),
    click.option(
        "--match-any",
        type=bool,
        is_flag=True,
        help="Flatten every filter value into one OR, ignoring the default grouping",
    ),
]

dry_run_option = click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would change without writing to the database or filesystem",
)

yes_option = click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt",
)

interactive_option = click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Confirm each item individually before applying changes",
)

# Individually named above so a command can take a subset by name.
global_click_confirmations = [dry_run_option, yes_option, interactive_option]

edit_click_options = [
    click.option(
        "--replace",
        "replace_value",
        required=True,
        help="The new value to write to the field",
    ),
    click.option(
        "--match",
        "match_pattern",
        default=None,
        metavar="PATTERN",
        help="Find this literal string within the field value and replace only that portion",
    ),
    click.option(
        "--multi",
        is_flag=True,
        help="Allow editing more than one track (required when filters match multiple tracks)",
    ),
    click.option(
        "--force",
        is_flag=True,
        help="Proceed past per-track safety gates that would otherwise skip a track (e.g. a FolderPath target that is missing or whose duration contradicts the track's stored length)",
    ),
]

convert_click_options = [
    click.option(
        "--delete-originals",
        type=click.Choice(["none", "lossless", "all"], case_sensitive=False),
        default="lossless",
        help="When to delete original files after conversion: 'lossless' deletes them only when no audio information was lost (down-sampling and MP3 output count as lossy), 'all' always deletes them, 'none' never deletes them (default: lossless)",
    ),
    click.option(
        "--overwrite",
        is_flag=True,
        help="Overwrite existing output files instead of skipping them",
    ),
    click.option(
        "--threads",
        "-t",
        type=click.IntRange(min=1),
        default=DEFAULT_THREADS,
        help=f"How many files to encode at once (default: {DEFAULT_THREADS}).",
    ),
    click.option(
        "--format-out",
        type=click.Choice(["aiff", "flac", "wav", "mp3"], case_sensitive=False),
        default="aiff",
        help="Output format (default: aiff)",
    ),
]


paths_argument = click.argument("paths", type=str, required=True, nargs=-1)

import_command_options = [
    click.option(
        "--to-playlist",
        "playlist",
        default=None,
        help="Add the tracks to this existing playlist (matched case-insensitively)",
    ),
]


database_path_option = click.option(
    "--database-path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    envvar="RBE_DATABASE_PATH",
    help="Path to master.db. Bypasses Rekordbox installation discovery.",
)


def add_click_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func

    return _add_options
