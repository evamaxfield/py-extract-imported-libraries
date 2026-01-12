#!/usr/bin/env python

from collections.abc import Callable
from pathlib import Path

import pytest

from eil import Extractor

###############################################################################

PY_EXAMPLE = """
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
"""

R_EXAMPLE = """
library(ggplot2)
require(dplyr)
data <- tidyr::gather(df, key, value)
"""

GO_EXAMPLE = """
import (
    "fmt"
    "github.com/gin-gonic/gin"
    "github.com/spf13/cobra"
)
"""

RUST_EXAMPLE = """
use serde::{Serialize, Deserialize};
use tokio::runtime::Runtime;
use std::collections::HashMap;
"""

JS_EXAMPLE = """
import React from 'react';
import { useEffect } from 'react';
import axios from 'axios';
import '@babel/core';
const express = require('express');
"""

INITIALIZED_EXTRACTOR = Extractor()

EXTRACTOR_SOURCE_CODE_FILE = Path(__file__).parent.parent / "main.py"


###############################################################################


@pytest.mark.parametrize(
    "code, extraction_func, expected_deps",
    [
        (
            PY_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_python_dependencies,
            {"numpy", "pandas", "sklearn"},
        ),
        (
            R_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_r_dependencies,
            {"ggplot2", "dplyr", "tidyr"},
        ),
        (
            GO_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_go_dependencies,
            {"github.com/gin-gonic/gin", "github.com/spf13/cobra"},
        ),
        (
            RUST_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_rust_dependencies,
            {"serde", "tokio"},
        ),
        (
            JS_EXAMPLE,
            INITIALIZED_EXTRACTOR.extract_javascript_dependencies,
            {"react", "axios", "@babel/core", "express"},
        ),
    ],
)
def test_dependency_extraction(
    code: str,
    extraction_func: Callable,
    expected_deps: set[str],
) -> None:
    extracted_deps = extraction_func(code)
    assert extracted_deps == expected_deps


def test_dependency_extraction_from_file() -> None:
    extracted_deps = INITIALIZED_EXTRACTOR.extract_from_file(EXTRACTOR_SOURCE_CODE_FILE)
    assert extracted_deps == {"tree_sitter", "tree_sitter_language_pack", "pathlib", "typing"}
