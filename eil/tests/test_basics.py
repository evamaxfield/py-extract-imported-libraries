#!/usr/bin/env python

from collections.abc import Callable
from pathlib import Path

import pytest

from eil import Extractor, ImportedLibraries

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
        "pathlib",
        "typing",
    }

    # Check third_party
    assert extracted_libs.third_party == {
        "tree_sitter",
        "tree_sitter_language_pack",
    }

    # Check first_party (data module)
    assert extracted_libs.first_party == {"data"}
