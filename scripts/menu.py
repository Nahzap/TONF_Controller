"""Menú serial de ejes, desde la carpeta del proyecto.

    .\\.venv\\Scripts\\python.exe .\\scripts\\menu.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tonf.__main__ import main


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main(["menu", *sys.argv[1:]]))
