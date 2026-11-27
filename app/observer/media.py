"""FFmpeg helpers: probe, frame extraction, tiny grayscale thumbnails for segmentation.

FFmpeg is called as a subprocess (no Python bindings). Install on macOS with
`brew install ffmpeg`.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

THUMB = 16  # 16x16 grayscale thumbnails for transition detection and aHash


class MediaError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise MediaError("ffmpeg/ffprobe not found on PATH. Install with `brew install ffmpeg`.")


def probe(path: Path) -> dict:
    require_ffmpeg()
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise MediaError(f"ffprobe failed: {out.stderr.strip()[:300]}")
    info = json.loads(out.stdout)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError("No video stream found.")
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    return {
        "duration_seconds": duration,
        "creation_time": container_creation_time(info),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "codec": video.get("codec_name"),
    }


# Preferred first: QuickTime's creationdate carries the local offset; creation_time is usually UTC.
CREATION_TAGS = ("com.apple.quicktime.creationdate", "creation_time")
EARLIEST_PLAUSIBLE_YEAR = 2005  # encoders write 1904/1970 epochs when no clock was set


def container_creation_time(info: dict) -> dict | None:
    """Recording creation time from container/stream tags (R6, D-027).

    Returns {"value": UTC ISO string, "tag": tag name, "raw": original} or None when absent, naive,
    malformed or implausible. It is the encoder's creation time, which may mark the start or the end of
    a screen recording; callers must keep its provenance.
    """
    tag_sets = [info.get("format", {}).get("tags") or {}]
    tag_sets += [s.get("tags") or {} for s in info.get("streams", [])]
    for tag in CREATION_TAGS:
        for tags in tag_sets:
            raw = next((v for k, v in tags.items() if k.lower() == tag), None)
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt.tzinfo is None or dt.year < EARLIEST_PLAUSIBLE_YEAR:
                continue
            if dt > datetime.now(timezone.utc) + timedelta(days=1):
                continue
            return {"value": dt.astimezone(timezone.utc).isoformat(), "tag": tag, "raw": str(raw)}
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _crop_filter(crop_width: float) -> str:
    crop_width = min(max(crop_width, 0.05), 1.0)
    if crop_width >= 0.999:
        return ""
    x = (1 - crop_width) / 2
    return f"crop=iw*{crop_width:.4f}:ih:iw*{x:.4f}:0,"


def extract_frames(path: Path, out_dir: Path, fps: float, width: int) -> list[Path]:
    """Extract JPEG frames at `fps` (for review UI and classifiers)."""
    require_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("frame_*.jpg"):
        old.unlink()
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-i", str(path),
        "-vf", f"fps={fps},scale={width}:-2",
        "-q:v", "4", str(out_dir / "frame_%05d.jpg"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise MediaError(f"ffmpeg frame extraction failed: {r.stderr.strip()[:300]}")
    return sorted(out_dir.glob("frame_*.jpg"))


def extract_thumbnails(path: Path, fps: float, crop_width: float) -> list[bytes]:
    """Return one 16x16 8-bit grayscale thumbnail per sampled frame (same timing as extract_frames)."""
    require_ffmpeg()
    vf = f"fps={fps},{_crop_filter(crop_width)}scale={THUMB}:{THUMB}:flags=area,format=gray"
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf, "-f", "rawvideo", "-"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise MediaError(f"ffmpeg thumbnail extraction failed: {r.stderr.decode()[:300]}")
    size = THUMB * THUMB
    data = r.stdout
    return [data[i:i + size] for i in range(0, len(data) - size + 1, size)]
