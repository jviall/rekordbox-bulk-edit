"""Edit API for rekordbox-edit."""

import logging

from pyrekordbox import Rekordbox6Database

from rekordbox_edit.api._utils import _order_tracks_by_op, stamp_usns, writing
from rekordbox_edit.api.field_handlers import FIELD_HANDLERS
from rekordbox_edit.errors import InputError
from rekordbox_edit.models import (
    EditRequest,
    EditOp,
    EditResponse,
    EditResult,
    SkippedTrack,
)
from rekordbox_edit.query import find_content_by_ids, get_filtered_content

logger = logging.getLogger(__name__)


def _classify_edit(
    db: Rekordbox6Database, content, args: EditRequest
) -> EditOp | SkippedTrack:
    """Return EditOp if this track should be edited, or SkippedTrack with
    reason if not."""
    handler = FIELD_HANDLERS[args.field]
    current = handler.current_value(content)
    new_value = handler.compute_new_value(current, args)
    if new_value is None or new_value == current:
        logger.debug(
            f"skip edit id={content.ID} reason=no_change "
            f"field={args.field} current={current!r}"
        )
        return SkippedTrack(id=str(content.ID), reason="no_change")
    skip_reason = handler.validate_track(db, content, str(new_value), args)
    if skip_reason is not None:
        logger.debug(
            f"skip edit id={content.ID} reason={skip_reason} field={args.field}"
        )
        return SkippedTrack(id=str(content.ID), reason=skip_reason)
    return EditOp(id=str(content.ID), new_value=str(new_value))


def _recheck_edit(
    db: Rekordbox6Database, content, op: EditOp, args: EditRequest
) -> EditOp | SkippedTrack:
    """Confirm an already-approved edit still holds.

    The op cleared validation during the preview, so a check that fails now
    means the file it named changed while the user was deciding.
    """
    handler = FIELD_HANDLERS[args.field]
    reason = handler.validate_track(db, content, op.new_value, args)
    if reason is not None:
        logger.debug(f"skip edit id={op.id} reason=db_or_fs_changed was={reason}")
        return SkippedTrack(id=op.id, reason="db_or_fs_changed")
    return op


def edit(
    db: Rekordbox6Database,
    args: EditRequest,
    *,
    dry_run: bool = False,
    ops: list[EditOp] | None = None,
) -> EditResponse:
    """Apply a metadata edit across tracks matching the filter args.

    With `dry_run=True`, returns the planned edits without any DB writes.
    With `dry_run=False` (default), commits the changes.

    Pass `ops` to apply an already-approved plan. No filter runs, so a row
    that started matching since the plan was made cannot join the edit; each
    op is re-checked against the filesystem and reported as
    `db_or_fs_changed` if it no longer holds.
    """
    logger.debug(f"edit start field={args.field} dry_run={dry_run}")
    handler = FIELD_HANDLERS.get(args.field)
    if handler is None:
        raise InputError(f"Unknown field: {args.field!r}")
    handler.validate_request(args)

    planned: list[EditOp] = []
    skipped: list[SkippedTrack] = []

    if ops is None:
        contents = get_filtered_content(db, args).scalars().all()
        logger.debug(f"edit fetched {len(contents)} candidate(s) from filter")
        for c in contents:
            result = _classify_edit(db, c, args)
            if isinstance(result, EditOp):
                planned.append(result)
            else:
                skipped.append(result)
        logger.debug(f"edit classified ops={len(planned)} skipped={len(skipped)}")

        if len(planned) > 1 and not args.multi:
            logger.debug(f"edit aborted on multi guard with {len(planned)} ops")
            raise InputError(
                f"Found {len(planned)} tracks that would be edited. "
                "Refine your filters, use dry_run to inspect, or pass multi=True to edit all."
            )
    else:
        rows = find_content_by_ids(db, [op.id for op in ops])
        contents = []
        for op in ops:
            content = rows.get(op.id)
            if content is None:
                logger.debug(f"skip edit id={op.id} reason=db_or_fs_changed row_gone")
                skipped.append(SkippedTrack(id=op.id, reason="db_or_fs_changed"))
                continue
            result = _recheck_edit(db, content, op, args)
            if isinstance(result, EditOp):
                planned.append(result)
                contents.append(content)
            else:
                skipped.append(result)
        logger.debug(f"edit re-checked ops={len(planned)} skipped={len(skipped)}")

    ops = planned

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

    new_values = {op.id: op.new_value for op in ops}
    old_values: dict[str, str | None] = {}
    edited = []
    with writing(db, "edit"):
        for content in contents:
            if str(content.ID) in new_values:
                old_values[str(content.ID)] = handler.current_value(content)
                handler.apply(db, content, new_values[str(content.ID)])
                edited.append(content)
        stamp_usns(db, edited)
        db.session.commit()
        logger.debug(f"edit committed {len(ops)} change(s) on field={args.field}")

        for content in contents:
            if str(content.ID) in new_values:
                handler.post_commit(db, content, old_values[str(content.ID)])

    return EditResponse(
        tracks=_order_tracks_by_op(contents, ops),
        result=EditResult(field=args.field, edits=ops, skipped=skipped),
    )
