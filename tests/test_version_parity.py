import json
from pathlib import Path

import daytrace


def test_python_and_npm_versions_are_synchronized() -> None:
    package = json.loads(Path("packages/daytrace-core/package.json").read_text())
    lock = json.loads(Path("packages/daytrace-core/package-lock.json").read_text())
    assert daytrace.__version__ == package["version"] == "0.4.0"
    assert lock["version"] == lock["packages"][""]["version"] == "0.4.0"
