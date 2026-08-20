"""Rich-based rendering for rekordbox-edit.

All rich Console output should go through the module-level ``console`` and be
drained to the debug log immediately after printing:

    console.print(...)
    logger.debug(console.export_text(clear=True))

Plain text output should continue to use ``logger.info()``.
"""

import logging
import os
from enum import Enum
from typing import Dict, Sequence

from rich import box
from rich.console import Console
from rich.table import Table

from rekordbox_edit.models import Track
from rekordbox_edit.utils import get_file_type_name, stored_to_star_rating

logger = logging.getLogger(__name__)

console = Console(record=True)


class PrintableField(Enum):
    """Track fields that can be printed in a table"""

    ID = "ID"
    FileNameL = "FileNameL"
    FolderPath = "FolderPath"
    FileType = "FileType"
    SampleRate = "SampleRate"
    BitDepth = "BitDepth"
    BitRate = "BitRate"
    ArtistName = "ArtistName"
    AlbumName = "AlbumName"
    Title = "Title"
    Comment = "Commnt"
    Rating = "Rating"


# Column headers shown in the rendered table
PRINT_HEADERS: Dict[PrintableField, str] = {
    PrintableField.ID: "ID",
    PrintableField.FileNameL: "File",
    PrintableField.Title: "Title",
    PrintableField.ArtistName: "Artist",
    PrintableField.AlbumName: "Album",
    PrintableField.FileType: "Type",
    PrintableField.SampleRate: "SampleRt",
    PrintableField.BitRate: "BitRt",
    PrintableField.BitDepth: "BitDp",
    PrintableField.FolderPath: "Folder",
    PrintableField.Comment: "Comment",
    PrintableField.Rating: "Rating",
}

# Per-column add_column kwargs. min_width guarantees a column is never collapsed
# to nothing; ratio distributes remaining terminal width among wide text columns.
_COLUMN_CONFIG: Dict[PrintableField, dict] = {
    PrintableField.ID: {"justify": "right", "min_width": 4},
    PrintableField.Title: {"min_width": 5, "ratio": 1},
    PrintableField.ArtistName: {"min_width": 5, "ratio": 1},
    PrintableField.AlbumName: {"min_width": 5, "ratio": 1},
    PrintableField.FileType: {"min_width": 4},
    PrintableField.SampleRate: {"min_width": 6},
    PrintableField.BitRate: {"min_width": 5},
    PrintableField.BitDepth: {"min_width": 4},
    PrintableField.FolderPath: {"min_width": 5, "ratio": 1},
    PrintableField.FileNameL: {"min_width": 5, "ratio": 1},
    PrintableField.Comment: {"min_width": 5, "ratio": 1},
    PrintableField.Rating: {"justify": "right", "min_width": 3},
}


def _cell_value(track: Track, column: PrintableField) -> str:
    """Render a single Track field as a string for a table cell."""
    if column is PrintableField.ID:
        return str(track.ID)
    if column is PrintableField.FileType:
        if track.FileType is None:
            return ""
        name = get_file_type_name(track.FileType)
        if name is None:
            logger.warning(
                f"Unexpected FileType [{track.FileType}] for track ID [{track.ID}]"
            )
            return "UNKNOWN"
        return name
    if column is PrintableField.FolderPath:
        return os.path.dirname(track.FolderPath or "")
    if column is PrintableField.Rating:
        return "" if track.Rating is None else str(stored_to_star_rating(track.Rating))
    value = getattr(track, column.value, None)
    return "" if value is None else str(value)


def print_track_info(
    content_list: Sequence[Track],
    print_columns: Sequence[PrintableField] | None = None,
    changed_field: PrintableField | None = None,
    new_values: Sequence[str] | None = None,
):
    """Print formatted track information.

    When ``changed_field`` and ``new_values`` are both provided, the matching
    column renders each row as a before/after preview: the old value is
    struck through and the new value is appended.
    """
    if (changed_field is None) != (new_values is None):
        raise ValueError("changed_field and new_values must be provided together")
    if new_values is not None and len(new_values) != len(content_list):
        raise ValueError(
            f"new_values length ({len(new_values)}) must match content_list length ({len(content_list)})"
        )

    if not content_list:
        return

    print_columns = print_columns or [
        PrintableField.ID,
        PrintableField.Title,
        PrintableField.FileType,
        PrintableField.SampleRate,
        PrintableField.BitDepth,
        PrintableField.FolderPath,
        PrintableField.FileNameL,
    ]
    if changed_field is not None and changed_field not in print_columns:
        print_columns = [*print_columns, changed_field]

    table = Table(show_header=True, box=box.SIMPLE, expand=True)
    table.add_column("#", justify="right", min_width=1, no_wrap=True)
    for column in print_columns:
        cfg = _COLUMN_CONFIG.get(column, {"min_width": 5})
        table.add_column(
            PRINT_HEADERS[column], no_wrap=True, overflow="ellipsis", **cfg
        )

    for i, track in enumerate(content_list, 1):
        cells = []
        for col in print_columns:
            old = _cell_value(track, col)
            if col is changed_field and new_values is not None:
                cells.append(f"[strike]{old}[/strike] [bold]{new_values[i - 1]}[/bold]")
            else:
                cells.append(old)
        table.add_row(str(i), *cells)

    console.print(table)
    logger.debug(console.export_text(clear=True))
