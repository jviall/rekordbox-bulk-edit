"""How much does each output format gain from converting several files at once?

Reports wall clock alongside the CPU time the ffmpeg children consumed. Their
ratio at one thread is the quantity that explains everything: it is how many
cores a *single* conversion already occupies, and therefore how little is left
for a pool of workers to overlap.

Run from the repository root:
    uv run python research/convert-thread-scaling/scripts/format_scaling.py
"""

import resource
import shutil
import sys
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _sources import COUNT, SECONDS, make_sources

WORK = Path("/tmp/rbe-thread-scaling")

TARGETS = (
    ("AIFF", "pcm_s16be", ".aiff", []),
    ("WAV", "pcm_s16le", ".wav", []),
    ("FLAC", "flac", ".flac", ["-sample_fmt", "s16"]),
    ("MP3", "libmp3lame", ".mp3", ["-b:a", "320k", "-sample_fmt", "s16p"]),
)


def encode(src: Path, codec: str, ext: str, extra: list[str]) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(src),
            "-acodec",
            codec,
            "-ar",
            "44100",
            *extra,
            str(WORK / "out" / f"{src.stem}-{codec}{ext}"),
        ],
        check=True,
        capture_output=True,
    )


def measure(sources, codec, ext, extra, threads) -> tuple[float, float]:
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(lambda s: encode(s, codec, ext, extra), sources))
    wall = time.perf_counter() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
    return wall, cpu


def main() -> None:
    sources = make_sources(WORK)
    print(f"{COUNT} files x {SECONDS}s\n")
    print(f"{'target':>6} {'threads':>8} {'wall':>7} {'cpu':>8} {'cores used':>11}")
    for label, codec, ext, extra in TARGETS:
        for threads in (1, 4):
            wall, cpu = measure(sources, codec, ext, extra, threads)
            print(
                f"{label:>6} {threads:>8} {wall:>7.2f} {cpu:>8.2f} {cpu / wall:>10.2f}x"
            )
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
