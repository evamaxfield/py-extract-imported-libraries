"""Supporting data for eil package."""

from pathlib import Path

from stdlib_list import long_versions, stdlib_list
from yaml import safe_load

DATA_DIR = Path(__file__).parent
STDLIBS_FILE = DATA_DIR / "stdlibs.yml"

###############################################################################


def load_stdlibs() -> dict[str, set[str]]:
    """Load standard library data from YAML file."""
    with open(STDLIBS_FILE) as f:
        stdlib_data: dict[str, list[str]] = safe_load(f)

    # Convert to set
    stdlib_data_as_set = {lang: set(libs) for lang, libs in stdlib_data.items()}

    # Add all versions of Python stdlib from stdlib-list package
    stdlib_data_as_set["python"] = set()
    for version in long_versions:
        stdlib_data_as_set["python"].update(stdlib_list(version))

    return stdlib_data_as_set
