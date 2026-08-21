"""Quantify grid/cue drift between two snapshots in DJ-relevant terms.

Reads two subject snapshots and reports how far the stage-B analysis sits from the
stage-A analysis: BPM delta, first-beat phase delta, per-beat phase drift (nearest-
neighbour, so it tolerates a differing beat count), key change, and per-cue drift
against each grid. Beats come from the `pqtz.times` array the snapshot stores.

    uv run python research/convert-reanalysis-impact/scripts/grid_drift.py <content_id> <stageA> <stageB>
"""

import bisect
import json
import sys
from pathlib import Path

if len(sys.argv) < 4:
    raise SystemExit("usage: grid_drift.py <content_id> <stageA> <stageB>")

cid, sa, sb = sys.argv[1], sys.argv[2], sys.argv[3]
EV = Path(__file__).resolve().parent.parent / "evidence"


def load(stage):
    return json.loads((EV / f"subject-{cid}-{stage}.json").read_text(encoding="utf-8"))


def grid(d):
    """Beat times in seconds (prefer DAT PQTZ), plus its summary."""
    for kind in ("DAT", "EXT"):
        pq = d["anlz"].get(kind, {}).get("pqtz")
        if pq and pq.get("times"):
            return pq["times"], pq
    return [], {}


def nearest(sorted_times, t):
    """Distance in seconds from t to the nearest value in sorted_times."""
    i = bisect.bisect_left(sorted_times, t)
    cands = []
    if i < len(sorted_times):
        cands.append(abs(sorted_times[i] - t))
    if i > 0:
        cands.append(abs(t - sorted_times[i - 1]))
    return min(cands) if cands else float("nan")


A, B = load(sa), load(sb)
ga, pa = grid(A)
gb, pb = grid(B)

print(f"# grid_drift {cid}: {sa} -> {sb}")

if not ga or not gb:
    print(f"  missing grid: A beats={len(ga)} B beats={len(gb)} (one side unanalyzed?)")
    raise SystemExit(0)

bpm_a = pa.get("bpm_avg")
bpm_b = pb.get("bpm_avg")
print(f"  BPM avg:      {bpm_a} -> {bpm_b}   delta {round((bpm_b - bpm_a), 3)}")
print(f"  beat count:   {len(ga)} -> {len(gb)}   delta {len(gb) - len(ga)}")
print(f"  first beat:   {ga[0] * 1000:.1f} ms -> {gb[0] * 1000:.1f} ms   "
      f"delta {round((gb[0] - ga[0]) * 1000, 1)} ms")

# Per-beat phase drift: each A beat to its nearest B beat.
gb_sorted = sorted(gb)
dists = [nearest(gb_sorted, t) * 1000 for t in ga]
mean_abs = sum(dists) / len(dists)
print(f"  phase drift (A beats vs nearest B beat): "
      f"mean {mean_abs:.1f} ms, max {max(dists):.1f} ms")

key_a = A["content"].get("KeyID")
key_b = B["content"].get("KeyID")
print(f"  KeyID:        {key_a} -> {key_b}   {'CHANGED' if key_a != key_b else 'same'}")

# Cue drift: how far each cue sits from the nearest beat, before vs after.
ga_sorted = sorted(ga)
cues_a = {(c.get("Kind"), c.get("InMsec")) for c in A.get("cues", [])}
if cues_a:
    print("  cue drift (ms to nearest beat, A-grid -> B-grid):")
    for kind, inmsec in sorted(cues_a, key=lambda x: (x[1] is None, x[1])):
        if inmsec is None:
            continue
        t = inmsec / 1000.0
        da = nearest(ga_sorted, t) * 1000
        db = nearest(gb_sorted, t) * 1000
        print(f"    Kind={kind} @ {inmsec} ms:  {da:.1f} -> {db:.1f} ms")
else:
    print("  cue drift: (no cues)")
