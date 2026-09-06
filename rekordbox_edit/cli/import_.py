"""Import CLI command."""

import logging

import click

from rekordbox_edit.cli._click import (
    add_click_options,
    global_click_confirmations,
    import_command_options,
    paths_argument,
    print_option,
)
from rekordbox_edit.api._import import (
    DirectoryConfirmationRequired,
    import_tracks,
)
from rekordbox_edit.cli._utils import (
    SCRIPTING_MODES,
    _build_args,
    _print_response_ids,
    _print_response_json,
    UserQuit,
    _validate_scripting_preconditions,
    confirm,
    with_database,
)
from rekordbox_edit.display import print_track_info
from rekordbox_edit.logger import PrintChoice, get_debug_file_path, set_level
from rekordbox_edit.models import ImportOp, ImportRequest

_logger = logging.getLogger(__name__)


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options(
    [
        *import_command_options,
        *global_click_confirmations,
        print_option,
    ]
)
@paths_argument
@with_database(writes=True)
def import_command(db, **kwargs):
    """Import audio files into the RekordBox database."""
    print_opt = kwargs.pop("print_opt", None)
    dry_run = kwargs.pop("dry_run", False)
    yes = kwargs.pop("yes", False)
    interactive = kwargs.pop("interactive", False)
    kwargs["paths"] = list(kwargs.get("paths") or ())
    # --yes authorizes a directory walk outright. A dry run writes nothing, and
    # previewing is how you inspect what a walk covers, so it walks freely too.
    # Anything else earns the walk from the prompt below.
    kwargs["recurse"] = yes or dry_run
    args = _build_args(ImportRequest, kwargs)
    set_level(print_opt)

    _validate_scripting_preconditions(
        print_opt,
        piped_stdin=False,
        dry_run=dry_run,
        yes=yes,
        interactive=interactive,
    )

    interactive_ok = print_opt not in SCRIPTING_MODES and not yes

    def _import_confirming_walk(request, **call_kwargs):
        """Import, turning the directory gate into a prompt when interactive.

        Returns (response, request_used); response is None when the user
        declined or quit the prompt.
        """
        try:
            return import_tracks(db, request, **call_kwargs), request
        except DirectoryConfirmationRequired as e:
            if not interactive_ok:
                raise click.UsageError(f"{e} Pass --yes to confirm.") from e
            _logger.info(str(e))
            try:
                if not confirm(
                    "Walk the directory and add these files?", default=False
                ):
                    return None, request
            except UserQuit:
                return None, request

        # Answered yes: one retry, which cannot reach the gate again. It can
        # still fail on the playlist name, which the gate preempted before.
        request = request.model_copy(update={"recurse": True})
        return import_tracks(db, request, **call_kwargs), request

    if yes or dry_run:
        response, _ = _import_confirming_walk(args, dry_run=dry_run)
        if response is None:
            return
        if (
            print_opt not in SCRIPTING_MODES
            and not response.result.added
            and not response.result.skipped
        ):
            _logger.info("Nothing to add.")
            return
        _print_import_result(response, print_opt, dry_run=dry_run)
        return

    preview, confirmed_args = _import_confirming_walk(args, dry_run=True)
    if preview is None:
        return
    if not preview.result.added:
        _logger.info("Nothing to add.")
        _report_skipped(preview)
        return

    # Reaching here means neither --yes nor --dry-run, which
    # _validate_scripting_preconditions has already established rules out a
    # scripting --print mode, so the preview always prints.
    print_track_info([op.track for op in preview.result.added])

    if interactive:
        chosen = _select_ops(preview)
        if not chosen:
            _logger.info("Cancelled.")
            return
    else:
        created, linked = _count_added(preview.result.added)
        try:
            if not confirm(f"{_add_summary(created, linked)}?", default=True):
                _logger.info("Cancelled.")
                return
        except UserQuit:
            return
        chosen = preview.result.added

    # Passing the previewed ops means no second directory walk, so a file
    # created during the prompt cannot be imported unseen, and the directory
    # gate cannot fire again.
    response = import_tracks(db, confirmed_args, ops=chosen)
    _print_import_result(response, print_opt, dry_run=False)


def _op_prompt(op: ImportOp, playlist: str | None) -> str:
    """The question for one pending op, phrased for what it will actually do.

    A create places the track in the playlist too when one was named, so it
    reads as one action rather than two.
    """
    name = op.track.FileNameL or op.path
    if op.action == "playlist_add":
        return f"  Place {name} in {playlist}?"
    if playlist:
        return f"  Add {name} and place it in {playlist}?"
    return f"  Add {name}?"


def _select_ops(preview) -> list[ImportOp]:
    """Walk the previewed ops, keeping the ones the user confirms."""
    playlist = preview.result.playlist
    chosen: list[ImportOp] = []
    for op in preview.result.added:
        try:
            if confirm(_op_prompt(op, playlist), default=True):
                chosen.append(op)
        except UserQuit:
            break
    return chosen


def _count_added(added: list[ImportOp]) -> tuple[int, int]:
    """(created, linked) counts split from a list of ImportOp by action."""
    created = sum(1 for op in added if op.action == "create")
    linked = len(added) - created
    return created, linked


def _add_summary(created: int, linked: int) -> str:
    """Describe a pending add as a yes/no question stem, e.g. 'Add 2 track(s)'.

    A playlist-only batch (no new rows, only existing tracks placed in a
    playlist) leads with the placement instead of an "Add 0 track(s)" count.
    """
    if created and linked:
        return (
            f"Add {created} track(s) and place {linked} existing track(s) "
            "in the playlist"
        )
    if linked:
        return f"Place {linked} existing track(s) in the playlist"
    return f"Add {created} track(s)"


def _report_added(created: int, linked: int) -> None:
    if created:
        _logger.info(f"Added {created} track(s).")
    if linked:
        _logger.info(f"Placed {linked} existing track(s) in the playlist.")


def _report_skipped(response) -> None:
    if response.result.skipped:
        _logger.info(f"{len(response.result.skipped)} file(s) skipped.")


def _print_import_result(response, print_opt, *, dry_run: bool) -> None:
    if not dry_run:
        created, linked = _count_added(response.result.added)
        _report_added(created, linked)
    _report_skipped(response)
    if print_opt == PrintChoice.IDS:
        _print_response_ids([op.id for op in response.result.added])
    elif print_opt == PrintChoice.JSON:
        _print_response_json(response)
    elif print_opt not in SCRIPTING_MODES and dry_run:
        print_track_info([op.track for op in response.result.added])
