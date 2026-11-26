"""Generate a synthetic 'screen recording' of N distinct Reels with FFmpeg.

Each Reel is a visually distinct, slightly animated pattern framed by a static
grey 'desktop UI' on both sides, like Reels on desktop web. Nothing here is
real Instagram content.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

PATTERNS = [
    "testsrc2=size=270x480:rate=10",
    "smptebars=size=270x480:rate=10",
    "mandelbrot=size=270x480:rate=10",
    "rgbtestsrc=size=270x480:rate=10",
    "cellauto=size=270x480:rate=10:rule=110",
    "life=size=270x480:rate=10:mold=10:ratio=0.3:seed=3",
]
HUES = [0, 180, 90, 270, 45, 135]


def make_reels_video(out: Path, durations: list[float]) -> Path:
    """Create an MP4 with len(durations) reels; returns the path."""
    out.parent.mkdir(parents=True, exist_ok=True)
    inputs, filters = [], []
    for i, d in enumerate(durations):
        src = PATTERNS[i % len(PATTERNS)]
        inputs += ["-f", "lavfi", "-t", f"{d}", "-i", src]
        filters.append(
            f"[{i}:v]hue=h={HUES[i % len(HUES)]},format=yuv420p,"
            f"pad=720:480:225:0:color=0x303030,setsar=1[v{i}]"
        )
    concat = "".join(f"[v{i}]" for i in range(len(durations))) + f"concat=n={len(durations)}:v=1:a=0[out]"
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters + [concat]),
           "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)
    return out


if __name__ == "__main__":
    import sys

    p = make_reels_video(Path(sys.argv[1] if len(sys.argv) > 1 else "synthetic_reels.mp4"), [6, 8, 5, 7, 6, 9])
    print(p)
