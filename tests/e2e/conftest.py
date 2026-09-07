"""End-to-end suite fixtures.

Tests in this directory drive the real CLI against a committed Rekordbox
`master.*.db` fixture. The suite is excluded from default collection via
`norecursedirs` in pyproject.toml; opt in with `RBE_RUN_E2E=1`.
"""

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol

import pytest
from syrupy.extensions.json import JSONSnapshotExtension

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO_ROOT / "tests/e2e/fixtures/audio"
DB_DIR_BY_PLATFORM = {
    "darwin": REPO_ROOT / "tests/e2e/fixtures/macos",
    "win32": REPO_ROOT / "tests/e2e/fixtures/windows",
    # Docker leg reuses the macOS fixture under Linux.
    "linux": REPO_ROOT / "tests/e2e/fixtures/macos",
}
# Canonical path each fixture DB records for every track's FolderPath. Audio
# must be staged here so the CLI's path resolution matches what Rekordbox wrote.
# macOS: /tmp is a symlink to /private/tmp, and Rekordbox stores the resolved
# form. Linux Docker has no such symlink — the literal /private/tmp path is
# created. Windows: the C:/rbedit-e2e tree was chosen by the fixture author.
STAGED_AUDIO_DIR_BY_PLATFORM = {
    "darwin": Path("/private/tmp/rbedit-e2e/music"),
    "linux": Path("/private/tmp/rbedit-e2e/music"),
    "win32": Path("C:/rbedit-e2e/music"),
}
STAGED_AUDIO_DIR = STAGED_AUDIO_DIR_BY_PLATFORM.get(sys.platform, Path("/tmp"))

# Snapshot key identifies which fixture DB is in play, not the host platform —
# the Docker (Linux) leg reuses the macOS DB and must match the same snapshot.
SNAPSHOT_KEY_BY_PLATFORM = {
    "darwin": "macos",
    "linux": "macos",
    "win32": "windows",
}
SNAPSHOT_KEY = SNAPSHOT_KEY_BY_PLATFORM.get(sys.platform, "unsupported")


@pytest.fixture(scope="session", autouse=True)
def _e2e_preconditions() -> None:
    """Gate the suite: opt-in via RBE_RUN_E2E=1, CI-or-Docker only.

    macOS and Windows runs must come from GitHub Actions (CI=true). Local dev
    runs go through the Linux Docker leg — host filesystem and Rekordbox
    install must not be touched.
    """
    if os.environ.get("RBE_RUN_E2E") != "1":
        pytest.skip("RBE_RUN_E2E=1 required to run the e2e suite")
    if sys.platform != "linux" and os.environ.get("CI") != "true":
        pytest.fail(
            "e2e tests on macOS/Windows run in CI only; "
            "use `make test-e2e-docker` for a local run."
        )
    db_dir = DB_DIR_BY_PLATFORM.get(sys.platform)
    if db_dir is None:
        pytest.fail(f"no e2e DB fixture mapped for sys.platform={sys.platform!r}")
    version = os.environ.get("RBE_DB_VERSION")
    if not version:
        pytest.fail(
            "RBE_DB_VERSION must be set to a Rekordbox DB version (e.g. 6.8.6)."
        )
    if not (db_dir / f"master.{version}.db").is_file():
        pytest.fail(f"no master.{version}.db under {db_dir}")


@pytest.fixture(scope="session")
def _db_source() -> Path:
    """Locate the fixture DB for the requested Rekordbox version.

    Version comes from the RBE_DB_VERSION env var so the CI matrix and local
    Docker runs can pin one DB at a time without filesystem ordering games.
    """
    version = os.environ["RBE_DB_VERSION"]
    return DB_DIR_BY_PLATFORM[sys.platform] / f"master.{version}.db"


@pytest.fixture(scope="session")
def db_path(_db_source: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Mutable working copy of the committed fixture; edits/convert mutate this."""
    work = tmp_path_factory.mktemp("rb-db")
    dst = work / _db_source.name
    shutil.copy(_db_source, dst)
    return dst


@pytest.fixture(scope="session", autouse=True)
def staged_audio(_e2e_preconditions: None) -> Iterator[Path]:
    """Stage audio at the absolute path the fixture DB records as FolderPath.

    Cleared and re-staged per session so the convert case starts from a known
    set (no leftover .mp3 from a prior aborted run).
    """
    if STAGED_AUDIO_DIR.exists():
        shutil.rmtree(STAGED_AUDIO_DIR)
    STAGED_AUDIO_DIR.mkdir(parents=True)
    for src in AUDIO_DIR.iterdir():
        if src.is_file():
            shutil.copy(src, STAGED_AUDIO_DIR / src.name)
    yield STAGED_AUDIO_DIR


class CliRun(Protocol):
    """Invoke the installed `rekordbox-edit` CLI against a fixture DB copy.

    Usage:
        result = cli("search", "--print", "json")
        result = cli("edit", "Title", "--replace", "X", "--yes", stdin="<ids>")
    """

    def __call__(
        self, command: str, *args: str, stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]: ...


def _run_cli(
    db_path: Path, command: str, *args: str, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "run",
            "rekordbox-edit",
            command,
            "--database-path",
            str(db_path),
            *args,
        ],
        input=stdin,
        capture_output=True,
        check=False,
        encoding="utf-8",
    )


@pytest.fixture
def cli(db_path: Path) -> CliRun:
    """Drive the CLI against the session-wide mutable copy the journey mutates."""

    def _run(
        command: str, *args: str, stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return _run_cli(db_path, command, *args, stdin=stdin)

    return _run


@pytest.fixture
def fresh_db(_db_source: Path, tmp_path: Path) -> Path:
    """A private copy of the fixture DB, isolated from the ordered journey
    suite and from every other test using it."""
    dst = tmp_path / _db_source.name
    shutil.copy(_db_source, dst)
    return dst


@pytest.fixture
def rbe(fresh_db: Path) -> CliRun:
    """Drive the CLI against this test's private DB copy."""

    def _run(
        command: str, *args: str, stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return _run_cli(fresh_db, command, *args, stdin=stdin)

    return _run


@pytest.fixture
def normalize(db_path: Path) -> Callable[[str], str]:
    """Replace the session's temp DB path with `<DB>` before snapshot comparison.

    Track IDs, audio paths under /tmp/rbedit-e2e/music, and metadata are
    stable across runs and deliberately left unnormalized — drift there is a
    regression we want to catch.
    """
    return lambda text: text.replace(str(db_path), "<DB>")


@pytest.fixture
def snapshot_json(snapshot):
    """Snapshot fixture that pretty-prints dict/list inputs as JSON.

    Stored as .json files under __snapshots__/, one per test, so diffs after a
    contract change land line-by-line instead of as a single mega-line.
    """
    return snapshot.use_extension(JSONSnapshotExtension)
