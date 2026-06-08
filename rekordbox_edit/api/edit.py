"""Edit API for rekordbox-edit."""

import logging

from pyrekordbox import Rekordbox6Database

from rekordbox_edit.api._utils import _order_tracks_by_op
from rekordbox_edit.models import (
    EditArgs,
    EditOp,
    EditResponse,
    EditResult,
    SkippedTrack,
)
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


def _classify_edit(content, args: EditArgs) -> EditOp | SkippedTrack:
    """Return EditOp if this track should be edited, or SkippedTrack with
    reason if not."""
    col_name = FIELD_COLUMNS[args.field]
    current = getattr(content, col_name)
    new_value = _compute_new_value(current, args.match_pattern, args.replace_value)
    if new_value is None or new_value == current:
        logger.debug(
            f"skip edit id={content.ID} reason=no_change "
            f"field={args.field} current={current!r}"
        )
        return SkippedTrack(id=str(content.ID), reason="no_change")
    return EditOp(id=str(content.ID), new_value=str(new_value))


def edit(
    db: Rekordbox6Database,
    args: EditArgs,
    *,
    dry_run: bool = False,
) -> EditResponse:
    """Apply a metadata edit across tracks matching the filter args.

    With `dry_run=True`, returns the planned edits without any DB writes.
    With `dry_run=False` (default), commits the changes.
    """
    logger.debug(f"edit start field={args.field} dry_run={dry_run}")
    contents = get_filtered_content(db, args).scalars().all()
    logger.debug(f"edit fetched {len(contents)} candidate(s) from filter")

    ops: list[EditOp] = []
    skipped: list[SkippedTrack] = []
    for c in contents:
        result = _classify_edit(c, args)
        if isinstance(result, EditOp):
            ops.append(result)
        else:
            skipped.append(result)
    logger.debug(f"edit classified ops={len(ops)} skipped={len(skipped)}")

    if len(ops) > 1 and not args.multi:
        logger.debug(f"edit aborted on multi guard with {len(ops)} ops")
        raise ValueError(
            f"Found {len(ops)} tracks that would be edited. "
            "Refine your filters, use dry_run to inspect, or pass multi=True to edit all."
        )

    if dry_run:
        logger.debug(f"edit dry-run return with {len(ops)} planned edit(s)")
        return EditResponse(
            tracks=_order_tracks_by_op(contents, ops),
            result=EditResult(field=args.field, edits=ops, skipped=skipped),
        )

    if not ops:
        return EditResponse(
            tracks=[],
            result=EditResult(field=args.field, edits=[], skipped=skipped),
        )

    assert db.session is not None

    col_name = FIELD_COLUMNS[args.field]
    new_values = {op.id: op.new_value for op in ops}
    for content in contents:
        if str(content.ID) in new_values:
            setattr(content, col_name, new_values[str(content.ID)])
    db.session.commit()
    logger.debug(f"edit committed {len(ops)} change(s) on field={args.field}")

    return EditResponse(
        tracks=_order_tracks_by_op(contents, ops),
        result=EditResult(field=args.field, edits=ops, skipped=skipped),
    )
