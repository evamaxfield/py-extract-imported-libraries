#!/usr/bin/env python

from collections.abc import Callable
from pathlib import Path

import pytest

from eil import Extractor, ExtractorType, ImportedLibraries

###############################################################################

PY_EXAMPLE = """
import os
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from .utils import helper_function
from ..config import settings
"""

R_EXAMPLE = """
library(ggplot2)
require(dplyr)
data <- tidyr::gather(df, key, value)
stats_result <- stats::lm(y ~ x)
source("helpers/data_utils.R")
source("../config/settings.R")
"""

INITIALIZED_EXTRACTOR = Extractor()

EXTRACTOR_SOURCE_CODE_FILE = Path(__file__).parent.parent / "main.py"


###############################################################################


@pytest.mark.parametrize(
    "code, extraction_func, expected_result",
    [
        (
            PY_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_python_libraries,
            ImportedLibraries(
                stdlib={"os", "sys"},
                third_party={"numpy", "pandas", "sklearn"},
                first_party={"utils", "config"},
            ),
        ),
        (
            R_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_r_libraries,
            ImportedLibraries(
                stdlib={"stats"},
                third_party={"ggplot2", "dplyr", "tidyr"},
                first_party={"data_utils", "settings"},
            ),
        ),
    ],
)
def test_library_extraction_comprehensive(
    code: str,
    extraction_func: Callable[[str], ImportedLibraries],
    expected_result: ImportedLibraries,
) -> None:
    """
    Test that all three categories
    (stdlib, third_party, first_party) are correctly extracted.
    """
    extracted_libs = extraction_func(code)
    assert extracted_libs.stdlib == expected_result.stdlib
    assert extracted_libs.third_party == expected_result.third_party
    assert extracted_libs.first_party == expected_result.first_party


def test_library_extraction_from_file() -> None:
    """Test extraction from the actual source file."""
    extracted_libs = INITIALIZED_EXTRACTOR.extract_from_file(EXTRACTOR_SOURCE_CODE_FILE)

    # Check stdlib
    assert extracted_libs.stdlib == {
        "collections",
        "dataclasses",
        "enum",
        "pathlib",
        "traceback",
        "typing",
    }

    # Check third_party
    assert extracted_libs.third_party == {
        "tqdm",
        "tree_sitter",
        "tree_sitter_language_pack",
    }

    # Check first_party (data module)
    assert extracted_libs.first_party == {"data"}


def test_directory_extraction() -> None:
    """Test extraction from a directory."""
    # Extract from the eil package directory (which contains main.py)
    eil_dir = Path(__file__).parent.parent
    result = INITIALIZED_EXTRACTOR.extract_from_directory(
        eil_dir,
        extractor_type=ExtractorType.PYTHON,
        recursive=False,
        show_progress=False,
    )

    # Should have extracted main.py and __init__.py (at least)
    assert len(result.extracted) >= 2
    assert len(result.failed) == 0

    # Find main.py in results and verify its extraction
    main_py = eil_dir / "main.py"
    assert main_py in result.extracted
    assert "tqdm" in result.extracted[main_py].third_party


def test_directory_extraction_recursive() -> None:
    """Test recursive extraction from a directory."""
    # Extract recursively from eil package directory
    eil_dir = Path(__file__).parent.parent
    result = INITIALIZED_EXTRACTOR.extract_from_directory(
        eil_dir,
        extractor_type=ExtractorType.PYTHON,
        recursive=True,
        show_progress=False,
    )

    # Should include files from subdirectories (tests/ and data/)
    assert (
        len(result.extracted) >= 4
    )  # main.py, __init__.py, data/__init__.py, tests/test_basics.py
    assert len(result.failed) == 0


def test_import_matches_repo_file_python(tmp_path: Path) -> None:
    """If a repo file has the same name as an import, it should be first-party."""
    extractor = Extractor()

    # Create a local module and a script that imports it
    (tmp_path / "utils.py").write_text("def helper():\n    return 1\n")
    app = tmp_path / "app.py"
    app.write_text("import utils\nimport requests\n")

    result = extractor.extract_from_directory(
        tmp_path, extractor_type=ExtractorType.PYTHON, recursive=False, show_progress=False
    )

    assert app in result.extracted
    libs = result.extracted[app]
    assert "utils" in libs.first_party
    assert "requests" in libs.third_party
    assert "utils" not in libs.third_party


def test_import_matches_repo_file_r(tmp_path: Path) -> None:
    """If a repo file has the same name as an R package import, it should be first-party."""
    extractor = Extractor()

    (tmp_path / "localpkg.R").write_text("myfunc <- function() {}\n")
    script = tmp_path / "script.R"
    script.write_text("library(localpkg)\nlibrary(ggplot2)\n")

    result = extractor.extract_from_directory(
        tmp_path, extractor_type=ExtractorType.R, recursive=False, show_progress=False
    )

    assert script in result.extracted
    libs = result.extracted[script]
    assert "localpkg" in libs.first_party
    assert "ggplot2" in libs.third_party
    assert "localpkg" not in libs.third_party


def test_import_matches_repo_dir_python(tmp_path: Path) -> None:
    """If a repo package directory has the same name as an import, it should be first-party."""
    extractor = Extractor()

    pkg_dir = tmp_path / "localpkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("def helper():\n    return 1\n")

    app = tmp_path / "app.py"
    app.write_text("import localpkg\nimport requests\n")

    result = extractor.extract_from_directory(
        tmp_path, extractor_type=ExtractorType.PYTHON, recursive=False, show_progress=False
    )

    assert app in result.extracted
    libs = result.extracted[app]
    assert "localpkg" in libs.first_party
    assert "requests" in libs.third_party
    assert "localpkg" not in libs.third_party


def test_import_matches_repo_dir_r(tmp_path: Path) -> None:
    """If a repo directory with R files matches a library import, it should be first-party."""
    extractor = Extractor()

    pkg_dir = tmp_path / "localpkg"
    pkg_dir.mkdir()
    (pkg_dir / "some.R").write_text("myfunc <- function() {}\n")

    script = tmp_path / "script.R"
    script.write_text("library(localpkg)\nlibrary(ggplot2)\n")

    result = extractor.extract_from_directory(
        tmp_path, extractor_type=ExtractorType.R, recursive=False, show_progress=False
    )

    assert script in result.extracted
    libs = result.extracted[script]
    assert "localpkg" in libs.first_party
    assert "ggplot2" in libs.third_party
    assert "localpkg" not in libs.third_party


def test_r_vector_not_misclassified(tmp_path: Path) -> None:
    """Ensure variables inside c(...) vectors are not considered imports."""
    extractor = Extractor()

    script = tmp_path / "vec.R"
    script.write_text("""
SALL_var <-c(
  S_growing_3_init=(No/12),
  A_growing_3_init=0,
  I_growing_3_init=0,
  C_growing_3_init=0,
  R_growing_3_init=0,
)

library(ggplot2)
""")

    result = extractor.extract_from_directory(
        tmp_path, extractor_type=ExtractorType.R, recursive=False, show_progress=False
    )

    assert script in result.extracted
    libs = result.extracted[script]
    assert "ggplot2" in libs.third_party
    # Ensure variable-like names are not reported as imports
    assert "S_growing_3_init" not in libs.third_party
    assert "C_growing_3_init" not in libs.third_party
    assert "localpkg" not in libs.third_party


def test_ignore_external_dir_python(tmp_path: Path) -> None:
    """Directories named 'external' (default) should be ignored when detecting
    first-party modules."""
    extractor = Extractor()

    ext = tmp_path / "external"
    ext.mkdir()
    (ext / "utils.py").write_text("def helper():\n    return 1\n")
    app = tmp_path / "app.py"
    app.write_text("import utils\n")

    # By default 'external' is ignored, so utils should NOT be detected as first-party
    result = extractor.extract_from_directory(
        tmp_path, extractor_type=ExtractorType.PYTHON, recursive=True, show_progress=False
    )
    assert app in result.extracted
    libs = result.extracted[app]
    assert "utils" not in libs.first_party
    assert "utils" not in libs.third_party
    # If we override to an empty ignore list, the module should be detected as first-party
    result2 = extractor.extract_from_directory(
        tmp_path,
        extractor_type=ExtractorType.PYTHON,
        recursive=True,
        show_progress=False,
        ignore_directories_list=set(),
    )
    libs2 = result2.extracted[app]
    assert "utils" in libs2.first_party


def test_ignore_imported_ignored_dir_python(tmp_path: Path) -> None:
    """Imports of an ignored directory name (e.g., 'ext') should be ignored."""
    extractor = Extractor()

    ext = tmp_path / "ext"
    ext.mkdir()
    (ext / "__init__.py").write_text("")
    app = tmp_path / "app.py"
    app.write_text("import ext\nimport requests\n")

    result = extractor.extract_from_directory(
        tmp_path,
        extractor_type=ExtractorType.PYTHON,
        recursive=True,
        show_progress=False,
    )

    assert app in result.extracted
    libs = result.extracted[app]
    assert "requests" in libs.third_party
    assert "ext" not in libs.third_party


def test_ignore_imported_vendored_dir_python(tmp_path: Path) -> None:
    """Imports that reference a vendored package (e.g.,
    'from vendored.blah import foo') should be ignored."""
    extractor = Extractor()

    vend = tmp_path / "vendored"
    vend.mkdir()
    (vend / "__init__.py").write_text("")
    (vend / "blah.py").write_text("def foo():\n    return 1\n")

    app = tmp_path / "app.py"
    app.write_text("from vendored.blah import foo\nimport numpy as np\n")

    result = extractor.extract_from_directory(
        tmp_path,
        extractor_type=ExtractorType.PYTHON,
        recursive=True,
        show_progress=False,
    )

    assert app in result.extracted
    libs = result.extracted[app]
    assert "numpy" in libs.third_party
    assert "vendored" not in libs.third_party


def test_ignore_external_dir_r(tmp_path: Path) -> None:
    """Directories named 'external' (default) should be ignored for R as
    well."""
    extractor = Extractor()

    ext = tmp_path / "external"
    ext.mkdir()
    (ext / "localpkg.R").write_text("myfunc <- function() {}\n")
    script = tmp_path / "script.R"
    script.write_text("library(localpkg)\n")

    # Default: ignored
    result = extractor.extract_from_directory(
        tmp_path,
        extractor_type=ExtractorType.R,
        recursive=True,
        show_progress=False,
    )
    assert script in result.extracted
    libs = result.extracted[script]
    assert "localpkg" not in libs.first_party
    assert "localpkg" not in libs.third_party

    # Override ignore list -> should detect as first-party
    result2 = extractor.extract_from_directory(
        tmp_path,
        extractor_type=ExtractorType.R,
        recursive=True,
        show_progress=False,
        ignore_directories_list=set(),
    )
    libs2 = result2.extracted[script]
    assert "localpkg" in libs2.first_party
