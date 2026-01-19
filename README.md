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

## Processing Notebook Formats

If you want to extract imports from Jupyter notebooks or Rmd files, you should first convert them to their script counterparts using: [py-nb-to-src](https://github.com/evamaxfield/py-nb-to-src) which will convert `.ipynb` of all types (R, Julia, Python, Matlab) to their respective script formats as well as `.Rmd` to `.R` scripts.

Install with: `pip install py-nb-to-src`

Then use the following code to convert and extract imports:

```python
from py_nb_to_src import convert_directory, ConverterType
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