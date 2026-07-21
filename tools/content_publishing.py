#!/usr/bin/env python3
"""Run the bundled CLI without installing the console script."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from content_publishing.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
