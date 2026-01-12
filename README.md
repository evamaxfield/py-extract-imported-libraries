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

```python
from eil import Extractor

extractor = Extractor()
imported_libs = extractor.extract_from_file("path/to/your/file.py")
print(imported_libs)
```

For example, here are the imported libraries extracted from the `main.py` file itself:

```python
from eil import Extractor

extractor = Extractor()
imported_libs = extractor.extract_from_file("main.py")
print(imported_libs)
# Output:
# ImportedLibraries(
#   stdlib={'collections', 'pathlib', 'dataclasses', 'typing'},
#   third_party={'tree_sitter_language_pack', 'tree_sitter'},
#   first_party={'data'},
# )
```