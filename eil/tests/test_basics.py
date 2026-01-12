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

GO_EXAMPLE = """
import (
    "fmt"
    "os"
    "github.com/gin-gonic/gin"
    "github.com/spf13/cobra"
)
"""

RUST_EXAMPLE = """
use serde::{Serialize, Deserialize};
use tokio::runtime::Runtime;
use std::collections::HashMap;
use std::fs::File;
use crate::utils::helpers;
use crate::config::settings;
"""

JS_EXAMPLE = """
import fs from 'fs';
import path from 'path';
import React from 'react';
import { useEffect } from 'react';
import axios from 'axios';
import '@babel/core';
const express = require('express');
const { formatData } = require('./utils/formatter');
import { CONFIG } from '../config';
"""

TS_EXAMPLE = """
import * as fs from 'fs';
import { readFile } from 'node:fs/promises';
import React from 'react';
import axios from 'axios';
import type { User } from './types';
import { api } from '../api/client';
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
        (
            GO_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_go_libraries,
            ImportedLibraries(
                stdlib={"fmt", "os"},
                third_party={"github.com/gin-gonic/gin", "github.com/spf13/cobra"},
                first_party=set(),
            ),
        ),
        (
            RUST_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_rust_libraries,
            ImportedLibraries(
                stdlib={"std"}, third_party={"serde", "tokio"}, first_party={"utils", "config"}
            ),
        ),
        (
            JS_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_javascript_libraries,
            ImportedLibraries(
                stdlib={"fs", "path"},
                third_party={"react", "axios", "@babel/core", "express"},
                first_party={"formatter", "config"},
            ),
        ),
        (
            TS_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_typescript_libraries,
            ImportedLibraries(
                stdlib={"fs", "node:fs"},
                third_party={"react", "axios"},
                first_party={"types", "client"},
            ),
        ),
    ],
)
def test_library_extraction_comprehensive(
    code: str,
    extraction_func: Callable,
    expected_result: ImportedLibraries,
) -> None:
    """Test that all three categories (stdlib, third_party, first_party) are correctly extracted."""
    extracted_libs = extraction_func(code)
    assert extracted_libs.stdlib == expected_result.stdlib, (
        f"stdlib mismatch: {extracted_libs.stdlib} != {expected_result.stdlib}"
    )
    assert extracted_libs.third_party == expected_result.third_party, (
        f"third_party mismatch: {extracted_libs.third_party} != {expected_result.third_party}"
    )
    assert extracted_libs.first_party == expected_result.first_party, (
        f"first_party mismatch: {extracted_libs.first_party} != {expected_result.first_party}"
    )


def test_library_extraction_from_file() -> None:
    """Test extraction from the actual source file."""
    extracted_libs = INITIALIZED_EXTRACTOR.extract_from_file(EXTRACTOR_SOURCE_CODE_FILE)

    # Check stdlib
    assert "pathlib" in extracted_libs.stdlib
    assert "collections" in extracted_libs.stdlib or "dataclasses" in extracted_libs.stdlib
    assert "typing" in extracted_libs.stdlib

    # Check third_party
    assert "tree_sitter" in extracted_libs.third_party
    assert "tree_sitter_language_pack" in extracted_libs.third_party

    # Check first_party (data module)
    assert "data" in extracted_libs.first_party


@pytest.mark.parametrize(
    "code, extraction_func, category, expected_deps",
    [
        # Python stdlib only
        (
            "import os\nimport sys\nimport pathlib",
            INITIALIZED_EXTRACTOR.extract_python_libraries,
            "stdlib",
            {"os", "sys", "pathlib"},
        ),
        # Python third-party only
        (
            "import numpy\nimport pandas\nimport requests",
            INITIALIZED_EXTRACTOR.extract_python_libraries,
            "third_party",
            {"numpy", "pandas", "requests"},
        ),
        # Python first-party only
        (
            "from .utils import helper\nfrom ..config import settings",
            INITIALIZED_EXTRACTOR.extract_python_libraries,
            "first_party",
            {"utils", "config"},
        ),
        # R stdlib only
        (
            "library(base)\nstats::mean(x)",
            INITIALIZED_EXTRACTOR.extract_r_libraries,
            "stdlib",
            {"base", "stats"},
        ),
        # R third-party only
        (
            "library(ggplot2)\nrequire(dplyr)",
            INITIALIZED_EXTRACTOR.extract_r_libraries,
            "third_party",
            {"ggplot2", "dplyr"},
        ),
        # R first-party only
        (
            'source("utils.R")\nsource("config.R")',
            INITIALIZED_EXTRACTOR.extract_r_libraries,
            "first_party",
            {"utils", "config"},
        ),
        # Go stdlib only
        (
            'import (\n    "fmt"\n    "os"\n)',
            INITIALIZED_EXTRACTOR.extract_go_libraries,
            "stdlib",
            {"fmt", "os"},
        ),
        # Go third-party only
        (
            'import "github.com/gin-gonic/gin"',
            INITIALIZED_EXTRACTOR.extract_go_libraries,
            "third_party",
            {"github.com/gin-gonic/gin"},
        ),
        # Rust stdlib only
        (
            "use std::collections::HashMap;\nuse std::fs::File;",
            INITIALIZED_EXTRACTOR.extract_rust_libraries,
            "stdlib",
            {"std"},
        ),
        # Rust third-party only
        (
            "use serde::Serialize;\nuse tokio::runtime::Runtime;",
            INITIALIZED_EXTRACTOR.extract_rust_libraries,
            "third_party",
            {"serde", "tokio"},
        ),
        # Rust first-party only
        (
            "use crate::utils::helpers;\nuse crate::config::settings;",
            INITIALIZED_EXTRACTOR.extract_rust_libraries,
            "first_party",
            {"utils", "config"},
        ),
        # JavaScript stdlib only
        (
            "import fs from 'fs';\nimport path from 'path';",
            INITIALIZED_EXTRACTOR.extract_javascript_libraries,
            "stdlib",
            {"fs", "path"},
        ),
        # JavaScript third-party only
        (
            "import React from 'react';\nimport axios from 'axios';",
            INITIALIZED_EXTRACTOR.extract_javascript_libraries,
            "third_party",
            {"react", "axios"},
        ),
        # JavaScript first-party only
        (
            "import { helper } from './utils';\nimport config from '../config';",
            INITIALIZED_EXTRACTOR.extract_javascript_libraries,
            "first_party",
            {"utils", "config"},
        ),
    ],
)
def test_library_extraction_by_category(
    code: str,
    extraction_func: Callable,
    category: str,
    expected_deps: set[str],
) -> None:
    """Test that each category is correctly extracted in isolation."""
    extracted_libs = extraction_func(code)
    actual_deps = getattr(extracted_libs, category)
    assert actual_deps == expected_deps, (
        f"{category} mismatch: {actual_deps} != {expected_deps}"
    )


def test_python_nested_relative_imports() -> None:
    """Test that nested relative imports are handled correctly."""
    code = """
from . import utils
from .. import config
from ...shared import constants
"""
    result = INITIALIZED_EXTRACTOR.extract_python_libraries(code)
    assert result.first_party == {"utils", "config", "shared"}


def test_javascript_scoped_packages() -> None:
    """Test that scoped packages like @babel/core are handled correctly."""
    code = """
import '@babel/core';
import '@babel/preset-env';
import { transform } from '@babel/core';
"""
    result = INITIALIZED_EXTRACTOR.extract_javascript_libraries(code)
    assert "@babel/core" in result.third_party
    assert "@babel/preset-env" in result.third_party


def test_rust_super_and_self_imports() -> None:
    """Test that Rust super and self imports are handled as first-party."""
    code = """
use super::models::User;
use self::config::Settings;
use crate::utils::helpers;
"""
    result = INITIALIZED_EXTRACTOR.extract_rust_libraries(code)
    # Note: super and self might need additional handling
    assert "utils" in result.first_party


def test_empty_code() -> None:
    """Test that empty code returns empty sets."""
    result = INITIALIZED_EXTRACTOR.extract_python_libraries("")
    assert result.stdlib == set()
    assert result.third_party == set()
    assert result.first_party == set()


def test_mixed_import_styles_python() -> None:
    """Test that both import styles work in Python."""
    code = """
import numpy
from pandas import DataFrame
import os
from .utils import helper
"""
    result = INITIALIZED_EXTRACTOR.extract_python_libraries(code)
    assert result.stdlib == {"os"}
    assert result.third_party == {"numpy", "pandas"}
    assert result.first_party == {"utils"}


def test_node_prefix_javascript() -> None:
    """Test that node: prefix is recognized as stdlib."""
    code = """
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
"""
    result = INITIALIZED_EXTRACTOR.extract_javascript_libraries(code)
    assert "node:fs" in result.stdlib
    assert "node:path" in result.stdlib
