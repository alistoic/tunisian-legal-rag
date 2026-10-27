"""Test root: ensures that the project root is on sys.path.

Without this file, pytest (default 'prepend' import mode) 
inserts the tests/ folder into sys.path instead of the project root, because tests/ isn't a package (no __init__.py).
The result: `import src...` and `import config` fail with ModuleNotFoundError, even if the code is correct. This conftest.py 
forces the explicit addition of the root.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
