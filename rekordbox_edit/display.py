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
from rich.console import Console

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

# Print header
PRINT_HEADERS: Dict[PrintableField, str] = {
    PrintableField.ID: f"{'ID':<{PRINT_WIDTHS[PrintableField.ID]}}",
    PrintableField.FileNameL: f"{'File':<{PRINT_WIDTHS[PrintableField.FileNameL]}}",
    PrintableField.Title: f"{'Title':<{PRINT_WIDTHS[PrintableField.Title]}}",
    PrintableField.ArtistName: f"{'Artist':<{PRINT_WIDTHS[PrintableField.ArtistName]}}",
    PrintableField.AlbumName: f"{'Album':<{PRINT_WIDTHS[PrintableField.AlbumName]}}",
    PrintableField.FileType: f"{'Type':<{PRINT_WIDTHS[PrintableField.FileType]}}",
    PrintableField.SampleRate: f"{'SampleRt':<{PRINT_WIDTHS[PrintableField.SampleRate]}}",
    PrintableField.BitRate: f"{'BitRt':<{PRINT_WIDTHS[PrintableField.BitRate]}}",
    PrintableField.BitDepth: f"{'BitDp':<{PRINT_WIDTHS[PrintableField.BitDepth]}}",
    PrintableField.FolderPath: f"{'FolderPath':<{PRINT_WIDTHS[PrintableField.FolderPath]}}",
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


def print_track_info(
    content_list: Sequence[DjmdContent],
    print_columns: Sequence[PrintableField] | None = None,
):
    """Print formatted track information"""
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

    # Calculate width for position column: 2 spaces + digits needed for max position
    pos_width = 2 + len(str(len(content_list)))
    header = f"{'#':<{pos_width}}" + "  ".join(
        map(lambda col: PRINT_HEADERS[col], print_columns)
    )
    logger.info(header)
    logger.info("-" * len(header))

    # Print each track
    for i, content in enumerate(content_list, 1):
        # Print row
        rows = {
            PrintableField.ID: f"{content.ID:<{PRINT_WIDTHS[PrintableField.ID]}}",
            PrintableField.FileNameL: f"{truncate_field(PrintableField.FileNameL, content.FileNameL):<{PRINT_WIDTHS[PrintableField.FileNameL]}}",
            PrintableField.Title: f"{truncate_field(PrintableField.Title, content.Title):<{PRINT_WIDTHS[PrintableField.Title]}}",
            PrintableField.AlbumName: f"{truncate_field(PrintableField.AlbumName, content.AlbumName):<{PRINT_WIDTHS[PrintableField.AlbumName]}}",
            PrintableField.ArtistName: f"{truncate_field(PrintableField.ArtistName, content.ArtistName):<{PRINT_WIDTHS[PrintableField.ArtistName]}}",
            PrintableField.FileType: f"{get_file_type_name(content.FileType):<{PRINT_WIDTHS[PrintableField.FileType]}}",
            PrintableField.SampleRate: f"{content.SampleRate:<{PRINT_WIDTHS[PrintableField.SampleRate]}}",
            PrintableField.BitRate: f"{content.BitRate:<{PRINT_WIDTHS[PrintableField.BitRate]}}",
            PrintableField.BitDepth: f"{content.BitDepth:<{PRINT_WIDTHS[PrintableField.BitDepth]}}",
            PrintableField.FolderPath: f"{truncate_field(PrintableField.FolderPath, content.FolderPath):<{PRINT_WIDTHS[PrintableField.FolderPath]}}",
        }

        row = f"{i:<{pos_width}}" + "  ".join(map(lambda col: rows[col], print_columns))

        logger.info(row)
    logger.info("")
