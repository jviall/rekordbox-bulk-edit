"""Rich-based rendering for rekordbox-edit.

All rich Console output should go through the module-level ``console`` and be
drained to the debug log immediately after printing:

    console.print(...)
    logger.debug(console.export_text(clear=True))

Plain text output should continue to use ``logger.info()``.
"""

import logging
from enum import Enum
from typing import Dict, Sequence

from pyrekordbox.db6 import DjmdContent
from rich import box
from rich.console import Console
from rich.table import Table

from rekordbox_edit.utils import get_file_type_name

logger = logging.getLogger(__name__)

console = Console(record=True)


class PrintableField(Enum):
    """Columns of DjmdContent that you can print"""

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


# Column widths (total ≈ 240 chars with spacing)
PRINT_WIDTHS: Dict[PrintableField, int] = {
    PrintableField.ID: 10,
    PrintableField.FileNameL: 25,
    PrintableField.Title: 25,
    PrintableField.ArtistName: 20,
    PrintableField.AlbumName: 20,
    PrintableField.FileType: 4,
    PrintableField.SampleRate: 8,
    PrintableField.BitRate: 5,
    PrintableField.BitDepth: 5,
    PrintableField.FolderPath: 80,
}

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
    PrintableField.FolderPath: "FolderPath",
}


def truncate_field(field: PrintableField, value: str | None):
    if value is None:
        return ""
    if len(value) <= PRINT_WIDTHS[field]:
        return value
    available = PRINT_WIDTHS[field] - 3  # Reserve 3 chars for "..."
    start_chars = available // 5 * 2
    end_chars = available - start_chars
    return f"{value[:start_chars]}...{value[-end_chars:]}"


def _cell_value(content: DjmdContent, column: PrintableField) -> str:
    """Render a single DjmdContent field as a string for a table cell."""
    if column is PrintableField.ID:
        return str(content.ID)
    if column is PrintableField.FileType:
        return get_file_type_name(content.FileType)
    if column in (PrintableField.SampleRate, PrintableField.BitRate, PrintableField.BitDepth):
        return str(getattr(content, column.value))
    return truncate_field(column, getattr(content, column.value))


def print_track_info(
    content_list: Sequence[DjmdContent],
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
        raise ValueError(
            "changed_field and new_values must be provided together"
        )
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
    ]

    table = Table(show_header=True, box=box.SIMPLE)
    table.add_column("#", justify="right")
    for column in print_columns:
        table.add_column(PRINT_HEADERS[column])

    for i, content in enumerate(content_list, 1):
        cells = []
        for col in print_columns:
            old = _cell_value(content, col)
            if col is changed_field and new_values is not None:
                cells.append(f"[strike]{old}[/strike] [bold]{new_values[i - 1]}[/bold]")
            else:
                cells.append(old)
        table.add_row(str(i), *cells)

    console.print(table)
    logger.debug(console.export_text(clear=True))
