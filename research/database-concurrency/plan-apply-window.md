# The Plan-Apply Window

One of two questions under [database-concurrency.md](database-concurrency.md), whose Terms section defines the database vocabulary used here.

## Question

Every write command in rekordbox-edit classifies twice. The CLI calls the API with `dry_run=True` to build a preview, blocks on a confirmation prompt, then calls the API again to apply, and the second call re-runs the filter query and the classifier from scratch. What can change between those two passes, and what does each command do when it does?

The question matters most for an interactive run, where the user may leave the prompt unanswered for minutes.

## Hypothesis

An earlier analysis held that a concurrent writer changing rows in that window makes the applied set diverge from the previewed one, silently. That analysis predates the single-writer advisory lock, which now excludes every other rekordbox-edit process for the duration of a command. The remaining writers are Rekordbox itself, which the user may allow past the running-Rekordbox prompt, and anything at all touching the filesystem.

## Method

Three probes isolate the database side, running against plain SQLite for portability. The database mechanics they rest on, and the terms used below, are recorded in [database-concurrency.md](database-concurrency.md). Each mirrors the shape of a real command: one `Session` opened for the whole command, a first query standing in for the preview, an outside writer on a separate connection standing in for Rekordbox, then a second query standing in for the apply pass.

- `scripts/snapshot_probe.py` reads through raw SQL text, isolating SQLite's own visibility rules from the ORM's.
- `scripts/identity_probe.py` reads through mapped objects, which is how `get_filtered_content` actually reads.
- `scripts/membership_probe.py` separates the value of a loaded row from the membership of the filtered set.

Output is recorded in `evidence/plan-apply-probes.txt`.

The filesystem side was established by reading the write paths rather than by probe: `api/edit.py`, `api/field_handlers.py`, `api/convert.py`, `api/import_.py`, and their CLI wrappers.

## Findings

### An Outside Writer Is Not Blocked, and Its Commit Is Visible

No read lock is held between statements, because the driver opens no transaction for a `SELECT`. See "The Driver Does Not Open a Transaction for a Read" in [database-concurrency.md](database-concurrency.md). The outside writer committed without waiting, and the second raw read returned the new value. A long confirmation prompt therefore does not hold the database still, and the earlier analysis was correct that the window is real.

### The Identity Map Makes Loaded Rows Stale, Not Fresh

Read through the ORM, the second pass returned the *same objects* as the first, carrying the *old* values, and `apply_pass[0] is preview[0]` held. The outside commit became visible only after an explicit `expire_all()`.

This inverts the practical concern. The apply pass does not silently act on newer column values than the preview showed. It acts on values that may be stale, which is the safer direction and matches what the user approved.

### Membership of the Filtered Set Does Drift

The `WHERE` clause runs in SQLite against live data, and only objects already loaded come from the identity map. A row that did not match during the preview and matches by the time of the apply pass is loaded fresh and joins the operation.

The probe demonstrates this: a preview matching one track applied to two, the second having been renamed underneath by the outside writer. The user approved one edit and would have received two.

Set membership, not column values, is the database-side exposure.

### The Filesystem Is Not Covered by Anything

No lock, session, or transaction constrains the filesystem, and all three commands consult it during classification.

`FolderPathField.validate_track` stats the target, compares its size against the stored `FileSize`, and probes its duration. Between passes a target can appear, vanish, or be replaced, so a track previewed as editable can become `file_not_found`, and a track the preview skipped can silently enter the applied set.

`_classify_convert` checks `os.path.exists(output_path)` and reports `output_file_exists`. A file appearing at that path between passes drops a track from the batch; one disappearing adds a track the preview never showed.

`import`'s `_expand_paths` re-walks every directory argument, and tags are re-read per file. Files created during the confirmation window are imported having never been previewed, and a file retagged in the window lands with metadata the user never saw. Directory arguments are exactly the high-count case, so this is the largest of the three exposures.

### Two Defects Found Along the Way

`cli/edit.py` guards `edit()` against `ValueError` on its preview calls (lines 76, 89, and 105) but not on either apply call (lines 134 and 142). The `--multi` guard raises `ValueError` when more than one op is classified without `multi` set. Since the apply pass reclassifies, a preview of exactly one op can become two, and the resulting `ValueError` reaches `main.py`'s unhandled-exception handler, which tells the user to file a GitHub issue against a routine condition.

`FolderPathField` holds `self._probes`, an instance dictionary keyed by content ID and path, and `FIELD_HANDLERS` binds one instance per field at module scope. That cache outlives a single request and is shared across both passes. It is harmless today because `validate_track` re-runs and overwrites each entry before `apply` reads it, but it is request state living on a process-global object.

## Conclusion

The window is real, and the advisory lock does not close it: Rekordbox and the filesystem both remain outside it.

The exposure is narrower than the original analysis stated, and differently shaped. Column values of rows the preview already saw do not drift, because the identity map returns the same stale objects. What drifts is which rows are in the set, and what the filesystem says about them.

Passing the planned ops into the write call closes the membership half by construction, since the apply pass would no longer run a filter query at all. It does not close the filesystem half, which still requires re-checking each op against disk at apply time. The difference is that such a check produces an explicit outcome rather than a silent one, which argues for a new `SkipReason` reported in the response. That is a change to the `--print json` schema and therefore a change to the public API, which is the decision the design has to settle rather than assume.

The two defects above are independent of that design and can be fixed on their own.
