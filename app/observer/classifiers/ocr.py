"""Optional local OCR via the `tesseract` binary (brew install tesseract). Runs on-device."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_image(path: Path, timeout: float = 20.0) -> str | None:
    if not ocr_available():
        return None
    try:
        r = subprocess.run(["tesseract", str(path), "-", "--psm", "6"], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    text = " ".join(r.stdout.split())
    return text or None
