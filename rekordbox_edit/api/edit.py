import logging

from pydantic import BaseModel
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import DjmdContent
from sqlalchemy import select

from rekordbox_edit.api._utils import _track_from_content
from rekordbox_edit.models import EditPlanArgs, Track
from rekordbox_edit.query import get_filtered_content

logger = logging.getLogger(__name__)

FIELD_COLUMNS: dict[str, str] = {
    "Title": "Title",
}


def _compute_new_value(
    current: str | int | None,
    match_pattern: str | None,
    replace_value: str | int,
) -> str | int | None:
    if current is None:
        return None
    if match_pattern is not None:
        return str(current).replace(match_pattern, str(replace_value))
    return replace_value


class EditPlan(BaseModel):
    field: str
    edits: list[tuple[Track, str]]


class EditResult(BaseModel):
    applied: int


def plan_edit(db: Rekordbox6Database, args: EditPlanArgs) -> EditPlan:
    """Compute which tracks would be changed and their new values.

    Raises ValueError if more than one track matches and args.multi is False.
    """
    result = get_filtered_content(db, args)
    tracks = result.scalars().all()

    col_name = FIELD_COLUMNS[args.field]
    edits: list[tuple[Track, str]] = []
    for content in tracks:
        current = getattr(content, col_name)
        new_value = _compute_new_value(current, args.match_pattern, args.replace_value)
        if new_value is None or new_value == current:
            continue
        edits.append((_track_from_content(content), str(new_value)))

    if len(edits) > 1 and not args.multi:
        raise ValueError(
            f"Found {len(edits)} tracks that would be edited. "
            "Refine your filters, use dry_run to inspect, or pass multi=True to edit all."
        )

    logger.debug(f"plan_edit: {len(edits)} edit(s) planned for field '{args.field}'")
    return EditPlan(field=args.field, edits=edits)


def edit(db: Rekordbox6Database, plan: EditPlan) -> EditResult:
    if not plan.edits:
        return EditResult(applied=0)

    assert db.session is not None

    col_name = FIELD_COLUMNS[plan.field]
    ids = [track.ID for track, _ in plan.edits]
    new_values = {track.ID: new_val for track, new_val in plan.edits}

    contents = (
        db.session.execute(select(DjmdContent).where(DjmdContent.ID.in_(ids)))
        .scalars()
        .all()
    )

    for content in contents:
        setattr(content, col_name, new_values[str(content.ID)])

    db.session.commit()
    logger.debug(f"edit: committed {len(contents)} change(s)")
    return EditResult(applied=len(contents))
