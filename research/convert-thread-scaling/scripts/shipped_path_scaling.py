"""Does the scaling hold through the code that actually ships?

The other two probes call ffmpeg directly, isolating its behavior from ours.
This one drives `_encode_one`, the function `convert()` submits to its pool, so
it measures the real path including the source probe, the codec check, and the
probe of the finished file.

Run from the repository root:
    uv run python research/convert-thread-scaling/scripts/shipped_path_scaling.py
"""

import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _sources import COUNT, SECONDS, make_sources

from rekordbox_edit.api.convert import _EncodeJob, _encode_one

WORK = Path("/tmp/rbe-shipped-scaling")

#: FLAC sources, so the codec check inside _encode_one passes.
_FLAC_FILE_TYPE = 5

TARGETS = (("AIFF", ".aiff"), ("MP3", ".mp3"))


def jobs_for(sources: list[Path], fmt: str, ext: str) -> list[_EncodeJob]:
    out = WORK / "out"
    return [
        _EncodeJob(
            op_id=str(i),
            source_path=str(src),
            file_name=src.name,
            file_type=_FLAC_FILE_TYPE,
            output_path=str(out / f"{src.stem}-{fmt}{ext}"),
            temp_path=str(out / f".rbe-convert-{i}-{src.stem}-{fmt}{ext}"),
            output_format=fmt,
        )
        for i, src in enumerate(sources)
    ]


def main() -> None:
    sources = make_sources(WORK)
    print(f"{COUNT} files x {SECONDS}s, through _encode_one\n")
    print(f"{'target':>6} {'threads':>8} {'wall':>7} {'speedup':>9}")
    for fmt, ext in TARGETS:
        baseline = None
        for threads in (1, 4):
            jobs = jobs_for(sources, fmt, ext)
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=threads) as pool:
                results = list(pool.map(_encode_one, jobs))
            wall = time.perf_counter() - start
            skipped = [r.skipped.reason for r in results if r.skipped]
            assert not skipped, f"unexpected skips: {skipped}"
            # _encode_one leaves the temp file for the caller to move.
            for job in jobs:
                Path(job.temp_path).unlink(missing_ok=True)
            baseline = baseline or wall
            print(f"{fmt:>6} {threads:>8} {wall:>7.2f} {baseline / wall:>8.2f}x")
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
