"""Reel segmentation: group sampled frames into distinct Reels.

Heuristic (see docs/DECISIONS.md D-006): a Reel transition on the desktop feed
is a large visual change in the centred video column. We compute the mean
absolute difference between consecutive 16x16 grayscale thumbnails and mark a
boundary where it exceeds an adaptive threshold, subject to a minimum segment
length so in-Reel cuts and the 1-2 frame scroll animation are not counted as
separate Reels. Results are suggestions: the review UI supports merge, split
and fully manual boundaries.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field


def frame_diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / max(len(a), 1)


def ahash(thumb: bytes) -> str:
    """64-bit average hash from a 16x16 grayscale thumbnail (downsampled to 8x8)."""
    side = int(len(thumb) ** 0.5)
    step = side // 8
    cells = []
    for by in range(8):
        for bx in range(8):
            vals = [thumb[(by * step + dy) * side + bx * step + dx] for dy in range(step) for dx in range(step)]
            cells.append(sum(vals) / len(vals))
    mean = sum(cells) / 64
    bits = 0
    for v in cells:
        bits = (bits << 1) | (1 if v >= mean else 0)
    return f"{bits:016x}"


@dataclass
class Segment:
    start_index: int
    end_index: int  # inclusive
    start_seconds: float
    end_seconds: float
    frame_indices: list[int] = field(default_factory=list)

    @property
    def representative_index(self) -> int:
        return self.frame_indices[len(self.frame_indices) // 2]


@dataclass
class SegmentationResult:
    segments: list[Segment]
    diffs: list[float]
    threshold: float
    params: dict


def detect_boundaries(diffs: list[float], offsets: list[float], *, abs_threshold: float,
                      min_segment_seconds: float, mad_k: float = 4.0) -> tuple[list[int], float]:
    """Return frame indices that start a new segment (excluding 0) and the threshold used.

    diffs[i] is the difference between frame i-1 and frame i (diffs[0] == 0).
    """
    body = diffs[1:]
    if not body:
        return [], abs_threshold
    med = statistics.median(body)
    mad = statistics.median([abs(d - med) for d in body]) or 1.0
    threshold = max(abs_threshold, med + mad_k * mad)
    boundaries: list[int] = []
    last_start_t = offsets[0]
    i = 1
    while i < len(diffs):
        if diffs[i] >= threshold:
            # A scroll animation spans several frames: take the peak of the run.
            j = i
            while j + 1 < len(diffs) and diffs[j + 1] >= threshold:
                j += 1
            peak = max(range(i, j + 1), key=lambda k: diffs[k])
            # Place the boundary after the animation settles (first frame past the run).
            start = min(j + 1, len(diffs) - 1) if j > i else peak
            if offsets[start] - last_start_t >= min_segment_seconds:
                boundaries.append(start)
                last_start_t = offsets[start]
            i = j + 1
        else:
            i += 1
    return boundaries, threshold


def segments_from_boundaries(n_frames: int, offsets: list[float], boundaries: list[int],
                             frame_interval: float) -> list[Segment]:
    starts = [0] + sorted(b for b in set(boundaries) if 0 < b < n_frames)
    segs = []
    for k, s in enumerate(starts):
        e = (starts[k + 1] - 1) if k + 1 < len(starts) else n_frames - 1
        segs.append(Segment(
            start_index=s, end_index=e,
            start_seconds=offsets[s], end_seconds=offsets[e] + frame_interval,
            frame_indices=list(range(s, e + 1)),
        ))
    return segs


def segment(thumbs: list[bytes], fps: float, *, abs_threshold: float = 28.0,
            min_segment_seconds: float = 3.0) -> SegmentationResult:
    n = len(thumbs)
    interval = 1.0 / fps
    offsets = [i * interval for i in range(n)]
    diffs = [0.0] + [frame_diff(thumbs[i - 1], thumbs[i]) for i in range(1, n)]
    if n == 0:
        return SegmentationResult([], [], abs_threshold, {})
    boundaries, thr = detect_boundaries(diffs, offsets, abs_threshold=abs_threshold,
                                        min_segment_seconds=min_segment_seconds)
    segs = segments_from_boundaries(n, offsets, boundaries, interval)
    return SegmentationResult(segs, diffs, thr, {
        "method": "thumb-diff-v1", "fps": fps, "abs_threshold": abs_threshold,
        "min_segment_seconds": min_segment_seconds, "threshold_used": round(thr, 2),
    })


def boundaries_from_offsets(offsets: list[float], boundary_seconds: list[float]) -> list[int]:
    """Map manual boundary timestamps (seconds) to frame indices."""
    out = []
    for t in boundary_seconds:
        idx = min(range(len(offsets)), key=lambda i: abs(offsets[i] - t))
        if idx > 0:
            out.append(idx)
    return sorted(set(out))
