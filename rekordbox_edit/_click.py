from enum import Enum
from pathlib import Path

import click


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
        help="Find tracks whose file paths include this value",
    ),
    click.option(
        "--exact-path",
        type=str,
        multiple=True,
        help="Find tracks whose file paths are exactly this value",
    ),
    click.option(
        "--format",
        type=click.Choice(["mp3", "flac", "aiff", "wav", "m4a"], case_sensitive=False),
        multiple=True,
        help="Find tracks of this format",
    ),
    click.option(
        "--match-all",
        type=bool,
        is_flag=True,
        help="Results must match all given filters",
    ),
]

global_click_confirmations = [
    click.option(
        "--dry-run",
        is_flag=True,
        help="Show what would change without writing to the database or filesystem",
    ),
    click.option(
        "--yes",
        "-y",
        is_flag=True,
        help="Skip confirmation prompt",
    ),
    click.option(
        "--interactive",
        "-i",
        is_flag=True,
        help="Confirm each item individually before applying changes",
    ),
]

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
]

convert_click_options = [
    click.option(
        "--delete/--keep",
        default=None,
        help="Delete or keep original files after conversion (default: delete for lossless, keep for MP3)",
    ),
    click.option(
        "--overwrite",
        is_flag=True,
        help="Overwrite existing output files instead of skipping them",
    ),
    click.option(
        "--format-out",
        type=click.Choice(["aiff", "flac", "wav", "alac", "mp3"], case_sensitive=False),
        default="aiff",
        help="Output format (default: aiff)",
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
