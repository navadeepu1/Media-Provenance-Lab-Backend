from pathlib import Path

root = Path(__file__).resolve().parents[1]
total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and ".git" not in p.parts)
if total >= 10 * 1024 * 1024:
    raise SystemExit(f"Repository is {total} bytes; must stay under 10 MB.")
print(f"Repository size: {total} bytes")

