"""Remove CLI command."""

import logging

import click

from rekordbox_edit.api._remove import remove
from rekordbox_edit.cli._click import (
    add_click_options,
    global_click_confirmations,
    global_click_filters,
    print_option,
    remove_click_options,
    track_ids_argument,
)
from rekordbox_edit.cli._utils import (
    SCRIPTING_MODES,
    UserQuit,
    _build_args,
    _handle_stdin,
    _print_response_ids,
    _print_response_json,
    _validate_scripting_preconditions,
    confirm,
    with_database,
)
from rekordbox_edit.display import print_track_info
from rekordbox_edit.logger import PrintChoice, get_debug_file_path, set_level
from rekordbox_edit.models import RemoveRequest

logger = logging.getLogger(__name__)

_SKIP_MESSAGES: dict[str, str] = {
    "db_or_fs_changed": "changed since the preview",
}


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options(
    [
        *remove_click_options,
        *global_click_confirmations,
        *global_click_filters,
        print_option,
        track_ids_argument,
    ]
)
@with_database(writes=True)
def remove_command(db, **kwargs):
    """Delete tracks from the Rekordbox library.

    Removes the database row, every record that references it, the track's
    analysis and artwork files, and any artist, album, genre, or label the
    removal leaves with no tracks behind it.

    The source audio file is kept by default. Pass --delete-source to delete
    it permanently.

    This cannot be undone. Back up your library before removing in bulk.
    """
    print_opt = kwargs.pop("print_opt", None)
    dry_run = kwargs.pop("dry_run", False)
    yes = kwargs.pop("yes", False)
    interactive = kwargs.pop("interactive", False)
    set_level(print_opt)
    piped_stdin = _handle_stdin(kwargs)
    args = _build_args(RemoveRequest, kwargs)
    _validate_scripting_preconditions(
        print_opt,
        piped_stdin=piped_stdin,
        dry_run=dry_run,
        yes=yes,
        interactive=interactive,
    )

    scripting_mode = print_opt in SCRIPTING_MODES

    if yes or dry_run:
        response = remove(db, args, dry_run=dry_run)
        _report_skips(response.result.skipped)
        _print_remove_result(response, print_opt, scripting_mode, dry_run=dry_run)
        return

    preview = remove(db, args, dry_run=True)
    _report_skips(preview.result.skipped)

    if not preview.result.removed:
        logger.info("No tracks matched.")
        return

    logger.info(f"Found {len(preview.result.removed)} track(s) to remove")
    if not scripting_mode:
        print_track_info([op.track for op in preview.result.removed])

    if interactive:
        selected_ids = []
        for op in preview.result.removed:
            try:
                if confirm(f"  Remove {op.track.FileNameL}?", default=True):
                    selected_ids.append(op.id)
            except UserQuit:
                break
        if not selected_ids:
            logger.info("Cancelled.")
            return
        chosen = set(selected_ids)
        selected = [op for op in preview.result.removed if op.id in chosen]
    else:
        selected = list(preview.result.removed)

    if not interactive:
        try:
            if not confirm(f"Remove {len(selected)} track(s)?", default=True):
                logger.info("Cancelled.")
                return
        except UserQuit:
            return

    try:
        args = _prompt_delete_source(args, len(selected))
    except UserQuit:
        return

    response = remove(db, args, ops=selected)
    _report_skips(response.result.skipped)
    _print_remove_result(response, print_opt, scripting_mode, dry_run=False)


def _prompt_delete_source(args, count: int):
    """Offer to delete the source audio files, which are kept by default.

    If the --delete-source flag is provided, the prompt is skipped.
    """
    if args.delete_source:
        return args
    if not confirm(f"Also delete {count} source file(s) from disk?", default=False):
        return args
    return args.model_copy(update={"delete_source": True})


def _report_skips(skipped) -> None:
    for reason, message in _SKIP_MESSAGES.items():
        count = sum(1 for s in skipped if s.reason == reason)
        if count:
            logger.warning(f"Skipping {count} track(s): {message}")


def _print_remove_result(response, print_opt, scripting_mode, *, dry_run: bool) -> None:
    if not dry_run:
        logger.info(f"\nRemoved {len(response.result.removed)} track(s)")
        sources = sum(1 for op in response.result.removed if op.source_deleted)
        if sources:
            logger.info(f"Deleted {sources} source file(s)")
        if response.result.deleted_relatives:
            logger.info(
                f"Deleted {response.result.deleted_relatives} unused "
                "artist/album/genre/label record(s)"
            )
    if print_opt == PrintChoice.IDS:
        _print_response_ids([op.id for op in response.result.removed])
    elif print_opt == PrintChoice.JSON:
        _print_response_json(response)
    elif not scripting_mode and dry_run:
        print_track_info([op.track for op in response.result.removed])
