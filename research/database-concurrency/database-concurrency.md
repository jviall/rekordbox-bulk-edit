# How master.db Behaves Under Concurrent Access

## Question

Rekordbox-edit is a single-writer tool by design, and a merged advisory lock now
enforces that between rekordbox-edit processes. Two writers remain outside that
lock: Rekordbox itself, which a user may allow past the running-Rekordbox prompt,
and the filesystem, which no database lock covers.

Two design questions ran into the same wall and prompted this investigation.

1. Every write command classifies twice, previewing and then re-classifying after
   a confirmation prompt. What can change in that window? Answered in
   [plan-apply-window.md](plan-apply-window.md).
2. Rekordbox tracks changes with a counter that rekordbox-edit does not maintain.
   Can that counter be maintained safely while Rekordbox may also be writing to
   it? Answered in [usn-maintenance.md](usn-maintenance.md).

This document records what both investigations established about `master.db`
itself, independent of either design. The two write-ups above depend on it.

## Terms

Definitions are scoped to how each term applies here, not to their full generality.

**SQLite.** The database engine Rekordbox uses. There is no server process: the
database is a single file, and every program that opens it coordinates with the
others through locks taken on that file. `master.db` is additionally encrypted
with SQLCipher, which changes how the file is read but not how it is locked.

**Transaction.** A group of statements that take effect together or not at all.
A transaction ends when it is *committed*, making its changes permanent and
visible to others, or *rolled back*, discarding them.

**Write lock.** SQLite permits one writer at a time. A connection acquires the
write lock when it first modifies data and holds it until it commits. Other
writers wait.

**Busy timeout.** How long a connection waits for a lock before giving up and
raising `database is locked`. A wait, not a failure, provided the holder commits
in time.

**Journal mode.** How SQLite keeps the database recoverable mid-write. Two modes
matter here. Under `DELETE`, the older default, changes are written in place and
the original pages are kept in a side file, which means readers and writers block
each other. Under `WAL` (write-ahead logging), changes are appended to a separate
log file, which lets readers proceed while a writer works.

**Snapshot.** Under WAL, a transaction that reads may be pinned to the database
as it stood at that moment, so later statements in the same transaction do not
see other connections' newer commits. Whether a snapshot is actually taken
depends on when the driver opens the transaction, which is the subject of a
finding below.

**Deferred and immediate.** `BEGIN` (deferred) opens a transaction without taking
any lock, acquiring one only when a statement needs it. `BEGIN IMMEDIATE` takes
the write lock up front.

**Lost update.** The failure mode where two writers each read a value, each add
to it, and each write back, so one writer's contribution disappears. Neither sees
an error. Avoiding it requires that the read and the write cannot be separated by
another writer's commit.

**Atomic.** Indivisible from another connection's point of view. A single
`UPDATE` that computes from the column's own value, such as
`SET int_1 = int_1 + 1`, is atomic in a way that reading the value and then
writing it back is not.

**SQLAlchemy.** The library that maps Python objects onto database rows, layered
under pyrekordbox. Two of its concepts appear repeatedly.

**Session.** SQLAlchemy's unit of work. Rekordbox-edit opens one per command and
holds it for the command's duration. A Session tracks the objects it has loaded
and the changes made to them, and issues a commit on request.

**Identity map.** The Session's cache of already-loaded rows, keyed by primary
key. Loading the same row twice in one Session returns the *same Python object*
both times, and the second load does not refresh its values from the database.

**USN.** Rekordbox's change counter, short for unique sequence number. Covered in
[usn-maintenance.md](usn-maintenance.md).

## Method

Probes run against a throwaway copy of the committed e2e fixture,
`tests/e2e/fixtures/macos/master.6.8.6.db`, through the SQLCipher engine
pyrekordbox builds, except where a claim is about SQLite generally rather than
about `master.db`, in which case plain SQLite is used for portability. Each probe
is named where it is cited. Scripts live in `scripts/`, output in `evidence/`.

Claims about rekordbox-edit's own behavior were established by reading
`cli/_utils.py`, `api/edit.py`, `api/field_handlers.py`, `api/convert.py`, and
`api/import_.py`.

## Findings

### master.db Uses WAL, Not DELETE

`PRAGMA journal_mode` returns `wal`. An earlier analysis of this repository
assumed `DELETE` and reasoned from it; that reasoning does not hold.

The practical consequence is that a reader never blocks a writer. Rekordbox-edit
holding a session open across a long confirmation prompt does not stop Rekordbox
from committing, and never did.

WAL also leaves `-wal` and `-shm` sidecar files beside the database. Any script
that copies the fixture must remove all three, or a later copy inherits pages
from an earlier run. An early version of these probes had that defect, and its
results moved between runs.

### The Driver Does Not Open a Transaction for a Read

This is the finding both investigations turned on, and it is not obvious from the
code.

SQLAlchemy reports `in_transaction() == True` for the whole span of a command.
The underlying pysqlite driver, which pysqlcipher inherits from, issues no `BEGIN`
before a `SELECT`. It issues one only before a statement that modifies data. So
rekordbox-edit's reads run in autocommit at the SQLite level while SQLAlchemy
believes a transaction is open, and no snapshot is taken.

`scripts/wal_snapshot.py` demonstrates this against the real engine: with
`in_transaction()` reporting `True` throughout, an outside writer committed and
the next read in the supposedly open transaction saw the new value.

Two consequences follow, one from each investigation.

Reads are not a consistent snapshot. Anything a command reads may be newer than
what it read a moment earlier, which is the mechanism behind the plan-apply
window.

Writes need no retry logic. A statement that modifies data opens its own write
transaction at that moment and reads current values, so it cannot fail with
`SQLITE_BUSY_SNAPSHOT` on an upgrade that never happens.

This rests on a driver default rather than on anything this repository controls.
Setting `isolation_level=None` on the connection, or a driver change, would
reverse both consequences.

### The Identity Map Hides Fresh Data From the ORM

The two paragraphs above describe SQL. Reading through mapped objects behaves
differently, and the difference matters.

`scripts/identity_probe.py` shows a second query in the same Session returning
the *same objects* as the first, carrying the *old* values, with
`apply_pass[0] is preview[0]` holding. The outside commit became visible only
after an explicit `expire_all()`.

So the same Session can be simultaneously fresh and stale: a `WHERE` clause is
evaluated by SQLite against current data, while the objects handed back for rows
already loaded carry the values they had when first read.

`scripts/membership_probe.py` separates the two effects. Which rows come back can
change; what an already-loaded row says cannot.

### Reading a Counter and Writing It Back Loses Updates

`scripts/concurrent_increment.py`, two writers against the real engine:

```
read-then-write  694 -> 719 (expected 744)   25 increment(s) LOST, errors: none
atomic-update    694 -> 744 (expected 744)   OK, no duplicate stamps
```

Exactly one writer's work vanished, silently. Expressing the increment as
`UPDATE ... SET int_1 = int_1 + :n` instead is exact, because the value is never
read into application code and so cannot go stale.

`RETURNING` is available for recovering the new value: SQLCipher reports SQLite
3.51.1, above the 3.35 that clause requires.

### The Busy Timeout Pragma Is Redundant at Its Current Value

Opening the fixture through pyrekordbox with rekordbox-edit not imported, so the
`connect` listener in `cli/_utils.py` is not registered, `PRAGMA busy_timeout`
already returns `5000`. The Python DBAPI sets it from `sqlite3.connect`'s default
`timeout=5.0`.

`BUSY_TIMEOUT_MS` is also `5000`, so the listener sets the value that is already
in effect. It is harmless, and it does nothing. Either raise it, so a queued
command waits longer than the default, or remove the listener.

## Conclusion

`master.db` is a WAL-mode SQLite database that permits one writer at a time and
never blocks readers. Rekordbox-edit's advisory lock excludes other rekordbox-edit
processes, so the writer it may actually contend with is Rekordbox.

The single most consequential property is that the driver opens no transaction
for a read. Rekordbox-edit's commands do not run against a stable view of the
database, which is what makes the plan-apply window reachable. The same property
means writes need no retry loop, which is what makes USN maintenance cheap.

Correctness for any shared value therefore has to come from the statement being
atomic, not from having checked beforehand that no one else was writing. A check
is a courtesy; the statement is the guarantee.
