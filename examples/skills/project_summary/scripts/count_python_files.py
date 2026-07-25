import sys
from pathlib import Path


root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
print(sum(1 for path in root.rglob("*.py") if path.is_file()))
