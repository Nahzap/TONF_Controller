"""Arranque de la suite desde la carpeta del proyecto.

    .\\.venv\\Scripts\\python.exe .\\scripts\\suite.py --listar
    .\\.venv\\Scripts\\python.exe .\\scripts\\suite.py
    .\\.venv\\Scripts\\python.exe .\\scripts\\suite.py --canal E1
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tonf.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main(["suite", *sys.argv[1:]]))
