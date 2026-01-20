# Extract Imported Libraries

Small Python utility to extract imported libraries from source code files in various programming languages using [tree-sitter](https://tree-sitter.github.io/tree-sitter/).

## Supported Languages

- Python
- R

# Installation

You can install the package via pip:

```bash
pip install pyeil
```


# Usage

## Single File

```python
from eil import Extractor

extractor = Extractor()
imported_libs = extractor.extract_from_file("path/to/your/file.py")
print(imported_libs)
# Output:
# ImportedLibraries(
#   stdlib={'os', 'sys'},
#   third_party={'requests', 'pandas'},
#   first_party={'utils'},
# )
```

## Directory Processing

Extract imports from all files in a directory with optional progress bar:

```python
from eil import Extractor, ExtractorType

extractor = Extractor()

# Extract from all supported files in a directory
result = extractor.extract_from_directory(
    "src/",
    extractor_type=ExtractorType.ALL,  # or PYTHON, R
    recursive=True,                     # search subdirectories
    show_progress=True,                 # show tqdm progress bar
)

# Access results
for file_path, libs in result.extracted.items():
    print(f"{file_path}: {libs.third_party}")

# Check for failures
for file_path, error in result.failed.items():
    print(f"Failed: {file_path}\n{error}")
```

## Ignored External/Vendored Directories

By default, directories commonly used for vendored or copied code (e.g., `external`, `vendor`, `third_party`, `deps`) are ignored when extracting imports from a repository. This prevents analyzing large bundled dependencies and avoids falsely classifying those packages as first-party.

Ignored directories are not scanned for the purpose of promoting module names to first-party or adding them to a third-party whitelist. If you want the analyzer to consider those directories, override the default ignore list by passing `ignore_directories_list=set()` to `Extractor.extract_from_directory()`.

Example:

```python
from eil import Extractor, ExtractorType

extractor = Extractor()
result = extractor.extract_from_directory(
    "src/",
    extractor_type=ExtractorType.ALL,
    recursive=True,
    ignore_directories_list=set(),  # disable default ignore list
)

# Proceed with `result.extracted` as usual
```
## Processing Notebook Formats

If you want to extract imports from Jupyter notebooks or Rmd files, you should first convert them to their script counterparts using: [py-nb-to-src](https://github.com/evamaxfield/py-nb-to-src) which will convert `.ipynb` of all types (R, Julia, Python, Matlab) to their respective script formats as well as `.Rmd` to `.R` scripts.

Install with: `pip install py-nb-to-src`

Then use the following code to convert and extract imports:

```python
from nb_to_src import convert_directory, ConverterType
from eil import Extractor

converted_file_results = convert_directory(
    "notebooks/",
    # recursive=True,
    progress_leave=False,
)
extractor = Extractor()
extracted_results = extractor.extract_from_directory(
    "notebooks/",
    # recursive=True,
    progress_leave=False,
)
for file_path, libs in extracted_results.extracted.items():
    print(f"{file_path}: {libs.third_party}")
```