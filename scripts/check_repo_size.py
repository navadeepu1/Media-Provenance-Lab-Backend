from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
tracked = subprocess.run(
    ["git", "-C", str(root), "ls-files", "-z"],
    check=True,
    capture_output=True,
).stdout.split(b"\0")
total = sum(
    path.stat().st_size
    for relative in tracked
    if relative
    for path in [root / relative.decode()]
    if path.is_file()
)
if total >= 10 * 1024 * 1024:
    raise SystemExit(f"Repository is {total} bytes; must stay under 10 MB.")
print(f"Repository size: {total} bytes")
