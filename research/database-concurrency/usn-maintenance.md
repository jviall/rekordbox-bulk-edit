# Maintaining USNs Safely Alongside a Running Rekordbox

One of two questions under [database-concurrency.md](database-concurrency.md), whose Terms section defines the database vocabulary used here.

## Question

Rekordbox tracks changes with a USN, or unique sequence number: a global counter
in `agentRegistry.localUpdateCount` and a per-row `rb_local_usn` stamp. Every
rekordbox-edit write command commits through `db.session.commit()` and maintains
neither, as recorded in
`../import-track-row-shape/decisions/commit-semantics-and-usn.md`.

Closing that gap means incrementing a counter that a running Rekordbox may also
be incrementing. Rekordbox-edit's advisory lock excludes other rekordbox-edit
processes but has no authority over Rekordbox itself. Can the increment be made
safe against a concurrent writer, and what does that cost?

## Hypothesis

Read-modify-write of a shared counter is the classic lost-update shape, so
today's `autoincrement_local_update_count` should lose increments under
concurrency. The textbook fix is `BEGIN IMMEDIATE`, which takes the write lock
before the read.

`BEGIN IMMEDIATE` applied to the engine would be costly here, since rekordbox-edit
opens one session per command and a long dry run would then hold a write lock for
its whole duration. An expression-form `UPDATE` that never reads into application
code should be equivalent and far cheaper.

## Method

All probes run against a throwaway copy of the committed e2e fixture,
`tests/e2e/fixtures/macos/master.6.8.6.db`, through the real SQLCipher engine
pyrekordbox builds, rather than against plain SQLite. Two `Rekordbox6Database`
instances stand in for two writers.

- `scripts/concurrent_increment.py` runs both candidate shapes under two
  concurrent writers.
- `scripts/block_reservation.py` checks that a whole block of USNs can be
  reserved in one statement, and what happens when an outside writer commits
  after ours has already read.
- `scripts/wal_snapshot.py` repeats the interleaving with `in_transaction()`
  instrumentation, so a session that quietly closed its transaction cannot be
  mistaken for one holding a read snapshot across the outside commit.

Output is recorded in `evidence/usn-spikes.txt`.

## Findings

### The Database Is in WAL Mode

`PRAGMA journal_mode` returns `wal`, not the DELETE mode an earlier analysis
assumed. Readers therefore never block writers, and a long confirmation prompt
cannot hold Rekordbox still.

This also affects fixture handling. WAL leaves `-wal` and `-shm` sidecars beside
the file, and an early version of these probes removed only the `.db`, letting a
later copy inherit the previous run's committed pages. Any script that copies the
fixture must remove all three.

### The Current Shape Loses Increments Silently

Two writers, 25 increments each, against the real engine:

```
read-then-write  694 -> 719 (expected 744)
  25 increment(s) LOST, errors: none
```

Exactly one writer's work vanished, and nothing raised. Both writers believed
they had succeeded. This is what `autoincrement_local_update_count` does today,
which is presumably why `db.commit()` refuses to run while Rekordbox is open.

### An Expression UPDATE Is Exact

```
atomic-update    694 -> 744 (expected 744)
  OK, errors: none, duplicate stamps handed out: 0
```

`UPDATE agentRegistry SET int_1 = int_1 + :n WHERE registry_id =
'localUpdateCount' RETURNING int_1` never reads the counter into application
code, so there is no window to lose. `RETURNING` hands back the new high value,
making the reserved block `high - n + 1 .. high`. SQLCipher reports SQLite
3.51.1, well above the 3.35 that `RETURNING` requires.

Reserving seven at once produced stamps 695 through 701 with the counter left at
701: contiguous, and ending exactly at the counter. That matches the shape
observed in a real library, where 906 imported tracks carried sequential values
ending exactly at `localUpdateCount`.

### No Retry Logic Is Needed

Under WAL, a transaction that has taken a read snapshot and then tries to write
after another connection has committed is expected to fail with
`SQLITE_BUSY_SNAPSHOT`. That would have forced a rollback-and-retry loop around
every commit.

It does not happen. With `in_transaction()` reporting `True` throughout, an
outside writer committed and moved the counter from 694 to 697, and our
subsequent reservation of two still succeeded, returning 699. It computed from
the fresh value, not from the 694 we had read.

The reason is the pysqlite driver's implicit-BEGIN behavior, which pysqlcipher
inherits: the driver issues no `BEGIN` for a `SELECT`, only before DML. So
rekordbox-edit's reads run in autocommit at the SQLite level even while
SQLAlchemy considers a transaction open, and the `UPDATE` opens the write
transaction itself, reading the counter as it stands at that moment.

This is the same driver behavior that makes the plan-apply window reachable, and
it is worth pinning with a test, since it depends on a driver default rather than
on anything this repository controls.

## Conclusion

The counter can be maintained safely without excluding Rekordbox. Correctness
comes from the statement being atomic, not from having checked for a process
beforehand, so the "Rekordbox is running, continue anyway?" affordance can stay
on its own merits rather than being load-bearing.

The design that follows:

1. Reserve USNs with one expression `UPDATE ... RETURNING`, in the same
   transaction as the row writes, so the reservation and the rows commit
   together.
2. Do not call `autoincrement_local_update_count`. Besides the lost-update
   shape, it walks `RekordboxAgentRegistry.__update_sequence__`, a class
   attribute shared by every instance in the process, which rekordbox-edit
   never clears.
3. Reserve one USN per row stamped. This will not reproduce rekordbox's
   numbering: in the sampled library 906 imported tracks hold 906 distinct
   stamps spread across the range 969 to 2694, so roughly 820 values in that
   span went to something else. What consumed them was never established, and
   the library's 259 artists and 303 albums are enough to account for much of
   it at one apiece. Matching rekordbox exactly would mean knowing everything
   it counts, and it does not matter: a high-water-mark consumer asks for rows
   above a value, so extra values cost nothing while a duplicate or reused
   stamp would hide a row. Uniqueness and monotonicity are the properties
   worth guaranteeing.
4. Keep write transactions short. The reservation holds the WAL write lock from
   the `UPDATE` until commit, and per-file commits in `convert` already bound
   that to one file.

The one fragility to record: this rests on the driver deferring `BEGIN` until the
first DML. Setting `isolation_level=None`, or a driver change, would reintroduce
the snapshot upgrade failure and with it the need for retry logic.
