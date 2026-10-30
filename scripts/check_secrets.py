import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
patterns = [r"AIza[0-9A-Za-z_-]{20,}", r"gsk_[0-9A-Za-z_-]{20,}", r"(?i)secret.{0,3}key\s*=\s*[^\s]+"] 
for path in root.rglob("*"):
    if not path.is_file() or ".git" in path.parts or path.name == ".env.example":
        continue
    text = path.read_text(errors="ignore")
    if any(re.search(pattern, text) for pattern in patterns):
        raise SystemExit(f"Possible secret in {path}")
print("No key-shaped secrets found.")

