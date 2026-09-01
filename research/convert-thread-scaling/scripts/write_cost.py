"""Is uncompressed output bound by the cost of writing it?

Runs the same FLAC decode and PCM conversion twice: once writing a real AIFF,
once discarding every byte through ffmpeg's null muxer. Any gap between them is
what writing costs.

Run from the repository root:
    uv run python research/convert-thread-scaling/scripts/write_cost.py
"""

import shutil
import sys
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _sources import make_sources

WORK = Path("/tmp/rbe-write-cost")


def _ffmpeg(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


def to_file(src: Path) -> None:
    _ffmpeg(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(src),
            "-acodec",
            "pcm_s16be",
            "-ar",
            "44100",
            str(WORK / "out" / f"{src.stem}.aiff"),
        ]
    )


def to_null(src: Path) -> None:
    _ffmpeg(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(src),
            "-acodec",
            "pcm_s16be",
            "-ar",
            "44100",
            "-f",
            "null",
            "-",
        ]
    )


def main() -> None:
    sources = make_sources(WORK)
    for label, fn in (("write AIFF", to_file), ("discard output", to_null)):
        for threads in (1, 4):
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=threads) as pool:
                list(pool.map(fn, sources))
            print(
                f"{label:>15}  threads={threads}  {time.perf_counter() - start:5.2f}s"
            )
    written = sum(f.stat().st_size for f in (WORK / "out").iterdir())
    print(f"\nbytes written by the first pair: {written / 1e6:.0f} MB")
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
