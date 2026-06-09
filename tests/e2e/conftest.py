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

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO_ROOT / "tests/e2e/fixtures/audio"
DB_DIR_BY_PLATFORM = {
    "darwin": REPO_ROOT / "tests/e2e/fixtures/macos",
    "win32": REPO_ROOT / "tests/e2e/fixtures/windows",
    # Docker leg (PR #7) reuses the macOS fixture under Linux.
    "linux": REPO_ROOT / "tests/e2e/fixtures/macos",
}
# Canonical path the fixture master.db references for every track's FolderPath.
# macOS resolves /tmp to /private/tmp before storing in the DB, so Rekordbox
# imports recorded under /tmp end up under /private/tmp. The literal path here
# satisfies both macOS (/tmp is a symlink to /private/tmp) and the Linux Docker
# leg (which has no such symlink and needs the exact path created).
STAGED_AUDIO_DIR = Path("/private/tmp/rbedit-e2e/music")


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
    dbs = sorted(db_dir.glob("master*.db"))
    if not dbs:
        pytest.fail(f"no master*.db under {db_dir}")


@pytest.fixture(scope="session")
def _db_source() -> Path:
    """Pick the highest-numbered master.*.db fixture for the current platform.

    When additional DB versions land (e.g. master.7.x.y.db), sorted picks the
    newest by lexicographic order, which matches semver for our naming.
    """
    return sorted(DB_DIR_BY_PLATFORM[sys.platform].glob("master*.db"))[-1]


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


CliRun = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def cli(db_path: Path) -> CliRun:
    """Invoke the installed `rekordbox-edit` CLI against the mutable fixture DB.

    Usage:
        result = cli("search", "--print", "json")
        result = cli("edit", "Title", "--replace", "X", "--yes", stdin="<ids>")
    """

    def _run(
        command: str, *args: str, stdin: str | None = None
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
            text=True,
            capture_output=True,
            check=False,
        )

    return _run


@pytest.fixture
def normalize(db_path: Path) -> Callable[[str], str]:
    """Replace the session's temp DB path with `<DB>` before snapshot comparison.

    Track IDs, audio paths under /tmp/rbedit-e2e/music, and metadata are
    stable across runs and deliberately left unnormalized — drift there is a
    regression we want to catch.
    """
    return lambda text: text.replace(str(db_path), "<DB>")
