# Why Convert Scales Unevenly Across Output Formats

## Question

`convert` encodes several files at once, bounded by `--threads`. Raising that
number helps some conversions far more than others. Which, by how much, and why?

The answer sets the flag's default and what the documentation should tell a user
about raising it.

## Hypothesis

The design notes behind `--threads` asserted that MP3 and FLAC output scale well
because their encoders are single-threaded per file, while WAV and AIFF output
is "close to pure I/O" and could get *slower* under concurrency on the external
and network drives DJs keep libraries on.

The ranking was assumed rather than measured, and the stated mechanism, that
uncompressed output is bound by writing, was never tested.

## Method

Three probes under `scripts/`, all against synthetic sources built by
`_sources.py`: eight five-minute pink-noise FLAC files, 182 MB in total. The
committed e2e audio fixtures are two seconds long, which measures process
startup rather than conversion. Pink noise compresses to roughly 43%, near the
50 to 60% a real music library sees, so the FLAC decode does representative work.

- `format_scaling.py` converts to all four supported targets at one thread and
  at four, reporting wall clock alongside the CPU time the ffmpeg children
  consumed.
- `write_cost.py` runs one conversion twice, once writing a real AIFF and once
  discarding every byte through ffmpeg's null muxer, isolating what writing
  costs.
- `shipped_path_scaling.py` repeats the comparison through `_encode_one`, the
  function `convert()` submits to its pool, confirming the effect survives the
  code that ships.

Output is recorded in `evidence/thread-scaling.txt`. Measurements come from an
Apple Silicon machine with internal storage.

## Findings

### Uncompressed Output Is Not Bound by Writing

The hypothesis is wrong. Writing 423 MB costs nothing measurable against
discarding the same output entirely:

```
     write AIFF  threads=1   1.65s      discard output  threads=1   1.63s
     write AIFF  threads=4   1.17s      discard output  threads=4   1.18s
```

The two are indistinguishable at both widths. Whatever limits AIFF conversion,
it is not the disk.

### Scaling Tracks How Many Cores One Conversion Already Uses

`format_scaling.py` reports CPU consumed against wall clock. That ratio at one
thread is how many cores a *single* conversion already occupies, and it predicts
the speedup exactly:

| target | 1 thread | 4 threads | speedup | cores one file uses |
| ------ | -------- | --------- | ------- | ------------------- |
| AIFF   | 1.63s    | 1.18s     | 1.38x   | 3.87                |
| WAV    | 1.60s    | 1.16s     | 1.38x   | 3.85                |
| FLAC   | 3.22s    | 1.45s     | 2.22x   | 2.18                |
| MP3    | 15.02s   | 3.82s     | 3.93x   | 1.26                |

The relationship is inverse and clean. ffmpeg already threads the FLAC decode
internally. AIFF and WAV output runs no encoder at all, so decoding is
essentially the whole job, one file already spreads across nearly four cores,
and a pool of workers has almost nothing left to overlap. libmp3lame is
single-threaded per file, occupies about 1.26 cores, and so parallelizes almost
perfectly. FLAC output sits between the two.

### Uncompressed Output Is Far Cheaper to Begin With

The absolute numbers matter more than the ratios. AIFF converts the same eight
tracks in 1.63 seconds against MP3's 15.02, roughly nine times faster. There is
little to win from parallelizing work that is already nearly free, which is a
better reason to leave WAV and AIFF alone than any claim about storage.

### The Effect Survives the Shipped Code Path

Driving `_encode_one` rather than ffmpeg directly reproduces the same split,
with the fixed overhead of the source probe and the codec check added:

```
  AIFF        1    2.27s      AIFF        4    1.41s     1.61x
   MP3        1   15.86s       MP3        4    4.07s     3.90x
```

## Conclusion

Raising `--threads` is worth it for MP3 output, marginal for FLAC, and close to
pointless for WAV and AIFF. The practical ranking in the original design notes
holds; the mechanism given for it does not.

The correct explanation is that ffmpeg already parallelizes the decode, so the
gain from converting several files at once is roughly the number of spare cores
divided by the number a single conversion already occupies. Output formats
without an encoder leave no spare cores to use.

A default of `min(4, os.cpu_count() or 1)` captures nearly all of the MP3 win,
which is the case where a win exists, and costs nothing in the cases where it
does not.

Two limits on these numbers. They come from one machine with internal storage,
so a spinning or network drive could behave differently, though `write_cost.py`
says writing is not the constraint that would change. And they measure ffmpeg's
current threading behavior, which is a property of the installed build rather
than of this repository.
