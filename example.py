from extractor import Extractor

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

###############################################################################


def main():
    # Init extractor
    extractor = Extractor()
    examples_map = {
        "Python": (PY_EXAMPLE, extractor.extract_python_dependencies),
        "R": (R_EXAMPLE, extractor.extract_r_dependencies),
        "Go": (GO_EXAMPLE, extractor.extract_go_dependencies),
        "Rust": (RUST_EXAMPLE, extractor.extract_rust_dependencies),
        "JavaScript": (JS_EXAMPLE, extractor.extract_javascript_dependencies),
    }

    # Iter over examples and extract deps
    for lang, (code, extraction_func) in examples_map.items():
        print(f"{lang} example:")
        print("-" * 40)
        print(code)
        print()
        extracted_deps = extraction_func(code)
        print("Dependencies found:")
        print(sorted(extracted_deps))
        print()
        print("-" * 20)
        print()

    # Also run against extractor.py itself
    print("Extracting dependencies from extractor.py itself:")
    print("-" * 40)
    extractor_deps = extractor.extract_from_file("extractor.py")
    print("Dependencies found:")
    print(sorted(extractor_deps))
    print()
    print("-" * 20)
    print()


if __name__ == "__main__":
    main()