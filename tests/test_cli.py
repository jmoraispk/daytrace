from __future__ import annotations

import subprocess
import sys


def test_module_help_is_available() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "daytrace", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "activitywatch" in result.stdout
    assert result.stderr == ""
