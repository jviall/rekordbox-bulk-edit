from enum import Enum

import click


class OutputChoice(Enum):
    SILENT = "silent"
    IDS = "ids"
    NORMAL = "normal"


output_option = click.option(
    "--output",
    default="normal",
    type=click.Choice(OutputChoice, case_sensitive=False),
    help="Configures the command to only output a list of Track Database (DjmdContent) IDs. Can be used to pipe to another command.",
)

track_ids_argument = click.argument(
    "track-ids",
    type=str,
    required=False,
)

global_click_filters = [
    click.option(
        "--track-id",
        type=str,
        multiple=True,
        help="Filter by the given Database Track ID",
    ),
    click.option(
        "--track",
        type=str,
        multiple=True,
        help="Filter by Track names that include this value",
    ),
    click.option(
        "--exact-track",
        type=str,
        multiple=True,
        help="Filter by Track names that are exactly this value",
    ),
    click.option(
        "--playlist",
        type=str,
        multiple=True,
        help="Filter by the given Playlist name",
    ),
    click.option(
        "--artist",
        type=str,
        multiple=True,
        help="Filter by the given Artist name",
    ),
    click.option(
        "--album",
        type=str,
        multiple=True,
        help="Filter by the given Album name",
    ),
    click.option(
        "--exact-album",
        type=str,
        multiple=True,
        help="Filter by Track names that are exactly this value",
    ),
    click.option(
        "--format",
        type=click.Choice(["mp3", "flac", "aiff", "wav", "m4a"], case_sensitive=False),
        multiple=True,
        help="Filter by one or more audio formats",
    ),
    click.option(
        "--match-all",
        type=bool,
        is_flag=True,
        help="Results must match all given filters",
    ),
]


def add_click_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func

    return _add_options
