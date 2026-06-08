"""Search API for rekordbox-edit."""

import logging

from pyrekordbox import Rekordbox6Database

from rekordbox_edit.api._utils import _track_from_content
from rekordbox_edit.models import SearchArgs, SearchResponse
from rekordbox_edit.query import get_filtered_content

logger = logging.getLogger(__name__)


def search(db: Rekordbox6Database, args: SearchArgs) -> SearchResponse:
    logger.debug("search start")
    result = get_filtered_content(db, args)
    tracks = [_track_from_content(c) for c in result.scalars().all()]
    logger.debug(f"search returning {len(tracks)} track(s)")
    return SearchResponse(tracks=tracks)
