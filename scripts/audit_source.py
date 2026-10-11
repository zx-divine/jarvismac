"""Audit intended source/staged content without printing potential secrets."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOP = {".gitignore", ".env.example", "README.md", "BUILD-REPORT.md", "pyproject.toml", "run_jarvis.py", "Start-JARVIS.bat", "Setup-JARVIS.bat", "Package-JARVIS.bat", "requirements.txt", "requirements-dev.txt", "requirements-lock.txt", "requirements-offline-voice.txt", "requirements-macos.txt", "requirements-macos-dev.txt"}
PREFIXES = ("jarvis/", "tests/", "scripts/", "packaging/", ".github/workflows/")
SECRET = re.compile(r"AIza[A-Za-z0-9_-]{35}|(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{30,}|sk-(?:ant-)?[A-Za-z0-9_-]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")

def permitted(name):
    return (name in TOP or name.startswith(PREFIXES) or name in {"docs/VERIFICATION.md", "docs/CRASH-RECOVERY.md", "docs/MACOS.md", "docs/RELEASE-STATUS.md"}) and "__pycache__" not in name and not name.endswith((".pyc", ".bin", ".wav", ".log"))

def audit(entries):
    failures = []
    for name, data in entries:
        if not permitted(name) or len(data) > 1_000_000:
            failures.append(name + ": outside safe source manifest or too large")
            continue
        content = data.decode("utf-8-sig")
        if SECRET.search(content):
            failures.append(name + ": possible credential/private key")
        if re.search(r"(?i)C:[\\/]Users[\\/]", content):
            failures.append(name + ": personal absolute path")
    if failures:
        raise RuntimeError("Source audit failed:\n" + "\n".join(failures))

def source_entries():
    return [(p.relative_to(ROOT).as_posix(), p.read_bytes()) for p in ROOT.rglob("*") if p.is_file() and permitted(p.relative_to(ROOT).as_posix())]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--git", help="Git executable; audits staged contents instead of working source")
    args = parser.parse_args()
    if args.git:
        names = subprocess.check_output([args.git, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd=ROOT).decode().split("\0")
        entries = [(name, subprocess.check_output([args.git, "show", ":" + name], cwd=ROOT)) for name in names if name]
    else:
        entries = source_entries()
    audit(entries)
    for name, data in sorted(entries):
        print(name)
    print(f"Audited {len(entries)} safe source files; no credential signatures or personal absolute paths found.")

if __name__ == "__main__":
    main()
