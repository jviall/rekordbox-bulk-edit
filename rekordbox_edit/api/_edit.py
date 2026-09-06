"""Edit API for rekordbox-edit."""

import logging

from pyrekordbox import Rekordbox6Database

from rekordbox_edit.api._utils import (
    stamp_usns,
    track_from_content,
    writing,
)
from rekordbox_edit.api.field_handlers import FIELD_HANDLERS
from rekordbox_edit.errors import InputError
from rekordbox_edit.models import (
    EditOp,
    EditRequest,
    EditResponse,
    EditResult,
    SkippedTrack,
)
from rekordbox_edit.query import find_content_by_ids, get_filtered_content

_logger = logging.getLogger(__name__)


def _classify_edit(
    db: Rekordbox6Database, content, args: EditRequest
) -> EditOp | SkippedTrack:
    """Return EditOp if this track should be edited, or SkippedTrack with
    reason if not."""
    handler = FIELD_HANDLERS[args.field]
    current = handler.current_value(content)
    new_value = handler.compute_new_value(current, args)
    track = track_from_content(content)
    if new_value is None or new_value == current:
        _logger.debug(
            f"skip edit id={content.ID} reason=no_change "
            f"field={args.field} current={current!r}"
        )
        return SkippedTrack(reason="no_change", track=track)
    skip_reason = handler.validate_track(db, content, str(new_value), args)
    if skip_reason is not None:
        _logger.debug(
            f"skip edit id={content.ID} reason={skip_reason} field={args.field}"
        )
        return SkippedTrack(reason=skip_reason, track=track)
    return EditOp(id=str(content.ID), new_value=str(new_value), track=track)


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
        _logger.debug(f"skip edit id={op.id} reason=db_or_fs_changed was={reason}")
        return SkippedTrack(
            reason="db_or_fs_changed", track=track_from_content(content)
        )
    return op.model_copy(update={"track": track_from_content(content)})


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
    that started matching after the plan was made will not join the edit; each
    op is re-checked against the filesystem and reported as
    `db_or_fs_changed` if it no longer holds.
    """
    _logger.debug(f"edit start field={args.field} dry_run={dry_run}")
    handler = FIELD_HANDLERS.get(args.field)
    if handler is None:
        raise InputError(f"Unknown field: {args.field!r}")
    handler.validate_request(args)

    planned: list[EditOp] = []
    skipped: list[SkippedTrack] = []

    if ops is None:
        contents = get_filtered_content(db, args).scalars().all()
        _logger.debug(f"edit fetched {len(contents)} candidate(s) from filter")
        for c in contents:
            result = _classify_edit(db, c, args)
            if isinstance(result, EditOp):
                planned.append(result)
            else:
                skipped.append(result)
        _logger.debug(f"edit classified ops={len(planned)} skipped={len(skipped)}")
    else:
        rows = find_content_by_ids(db, [op.id for op in ops])
        contents = []
        for op in ops:
            content = rows.get(op.id)
            if content is None:
                _logger.debug(f"skip edit id={op.id} reason=db_or_fs_changed row_gone")
                skipped.append(SkippedTrack(reason="db_or_fs_changed", track=op.track))
                continue
            result = _recheck_edit(db, content, op, args)
            if isinstance(result, EditOp):
                planned.append(result)
                contents.append(content)
            else:
                skipped.append(result)
        _logger.debug(f"edit re-checked ops={len(planned)} skipped={len(skipped)}")

    ops = planned

    if dry_run:
        _logger.debug(f"edit dry-run return with {len(ops)} planned edit(s)")
        return EditResponse(
            result=EditResult(
                field=args.field, dry_run=True, edits=ops, skipped=skipped
            ),
        )

    if not ops:
        return EditResponse(
            result=EditResult(
                field=args.field, dry_run=dry_run, edits=[], skipped=skipped
            ),
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
        _logger.debug(f"edit committed {len(ops)} change(s) on field={args.field}")

        for content in contents:
            if str(content.ID) in new_values:
                handler.post_commit(db, content, old_values[str(content.ID)])

    # Refreshed post-commit: an op's track up to now is the pre-write
    # classification snapshot, and handler.apply() mutated the row in place
    # after that snapshot was taken.
    edited_by_id = {str(content.ID): content for content in edited}
    ops = [
        op.model_copy(update={"track": track_from_content(edited_by_id[op.id])})
        for op in ops
    ]

    return EditResponse(
        result=EditResult(
            field=args.field, dry_run=dry_run, edits=ops, skipped=skipped
        ),
    )
