"""Fix git merge conflicts: keep the 'theirs' version (after =======)."""
import sys
from pathlib import Path

files = [
    "backend/app/routes/alerts.py",
    "backend/app/routes/tweets.py",
    "backend/app/routes/auth.py",
    "backend/app/routes/targets.py",
]

for filepath in files:
    p = Path(filepath)
    if not p.exists():
        print(f"  SKIP: {filepath} not found")
        continue
    
    content = p.read_text(encoding="utf-8")
    if "<<<<<<< HEAD" not in content:
        print(f"  OK: {filepath} (no conflicts)")
        continue
    
    # Keep "theirs" version (after ======= until >>>>>>>)
    lines = content.split("\n")
    result = []
    skip = 0  # 0=normal, 1=skip ours, 2=keep theirs
    
    for line in lines:
        if line.startswith("<<<<<<< "):
            skip = 1  # start skipping "ours"
            continue
        elif line.startswith("======="):
            skip = 2  # start keeping "theirs"
            continue
        elif line.startswith(">>>>>>>"):
            skip = 0  # back to normal
            continue
        
        if skip != 1:
            result.append(line)
    
    p.write_text("\n".join(result), encoding="utf-8")
    print(f"  FIXED: {filepath}")

print("\nDone!")
