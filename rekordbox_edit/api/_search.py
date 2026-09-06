"""Search API for rekordbox-edit."""

import logging

from pyrekordbox import Rekordbox6Database

from rekordbox_edit.api._utils import track_from_content
from rekordbox_edit.models import SearchRequest, SearchResponse
from rekordbox_edit.query import get_filtered_content

_logger = logging.getLogger(__name__)


def search(db: Rekordbox6Database, args: SearchRequest) -> SearchResponse:
    _logger.debug("search start")
    result = get_filtered_content(db, args)
    tracks = [track_from_content(c) for c in result.scalars().all()]
    _logger.debug(f"search returning {len(tracks)} track(s)")
    return SearchResponse(tracks=tracks)
