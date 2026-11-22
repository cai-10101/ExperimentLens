"""Demonstrate that a real assertion catches a small bug in an isolated copy."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TARGET = "if not math.isfinite(number):"
BROKEN = "if False:"
TEST = "test_core.CoreTests.test_record_validation"


def run_test(root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(root / "src"), str(root / "tests")))
    return subprocess.run(
        [sys.executable, "-m", "unittest", TEST],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="experimentlens-test-sensitivity-") as temp:
        root = Path(temp)
        shutil.copytree(ROOT / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        shutil.copytree(ROOT / "tests", root / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        model = root / "src" / "experimentlens" / "model.py"
        original = model.read_text(encoding="utf-8")
        if original.count(TARGET) != 1:
            raise RuntimeError("finite-number check changed; update this demonstration")

        baseline = run_test(root)
        if baseline.returncode != 0:
            print(baseline.stderr, file=sys.stderr)
            raise RuntimeError("baseline test must pass before introducing the bug")

        model.write_text(original.replace(TARGET, BROKEN, 1), encoding="utf-8")
        broken = run_test(root)
        if broken.returncode == 0 or "FAIL" not in broken.stderr:
            print(broken.stderr, file=sys.stderr)
            raise RuntimeError("the deliberately broken copy was not caught by the test")

        model.write_text(original, encoding="utf-8")
        restored = run_test(root)
        if restored.returncode != 0:
            print(restored.stderr, file=sys.stderr)
            raise RuntimeError("restored code did not pass")

    print(f"{TEST}: baseline PASS, deliberate bug FAIL, restored PASS")
    print("Only a temporary copy was modified; repository sources were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
