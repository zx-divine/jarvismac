"""Launch a real package with isolated data and measure idle CPU/RSS."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import psutil

executable = Path(sys.argv[1]).resolve()
root = Path(sys.argv[2]).resolve()
root.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, JARVIS_DATA_DIR=str(root))
for key in list(env):
    if any(word in key.upper() for word in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")):
        env.pop(key)
started = time.monotonic()
process = subprocess.Popen([str(executable), "--smoke-test", "--lifecycle-test"], env=env)
observed = psutil.Process(process.pid)
samples = []
try:
    while process.poll() is None and time.monotonic() - started < 90:
        cpu = observed.cpu_percent(interval=1)
        elapsed = time.monotonic() - started
        phase_file = root / "phase.json"
        phase = json.loads(phase_file.read_text())["phase"] if phase_file.exists() else "startup"
        samples.append({"elapsed": round(elapsed, 1), "phase": phase, "cpu_percent_one_core": cpu, "rss_mb": round(observed.memory_info().rss / 2**20, 1)})
    if process.poll() is None:
        process.kill()
        raise RuntimeError("Packaged lifecycle check exceeded 90 seconds")
except (psutil.NoSuchProcess, psutil.AccessDenied):
    process.wait(timeout=90)
report = {"exit_code": process.wait(), "elapsed_seconds": round(time.monotonic() - started, 2), "samples": samples}
(root / "performance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key != "samples"}))
if (root / "launch-check.json").exists():
    print((root / "launch-check.json").read_text())
raise SystemExit(report["exit_code"])
