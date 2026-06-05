from pyrekordbox import Rekordbox6Database

from rekordbox_edit.api._utils import _track_from_content
from rekordbox_edit.args import FilterArgs, Track
from rekordbox_edit.query import get_filtered_content


def search(db: Rekordbox6Database, args: FilterArgs) -> list[Track]:
    result = get_filtered_content(db, args)
    return [_track_from_content(c) for c in result.scalars().all()]
