"""Content Publishing SOP command and transaction core."""

from pathlib import Path
from importlib import metadata


def _read_version() -> str:
    candidate = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return candidate.read_text(encoding="utf-8").strip()
    except OSError:
        try:
            return metadata.version("content-publishing-sop")
        except metadata.PackageNotFoundError:
            return "0.2.0"


__version__ = _read_version()
