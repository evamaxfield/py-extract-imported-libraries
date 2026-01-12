# Extract Imported Libraries

Small Python utility to extract imported libraries from source code files in various programming languages using [tree-sitter](https://tree-sitter.github.io/tree-sitter/).

## Supported Languages

- Python
- R
- Go
- Rust
- JavaScript
- TypeScript

# Usage

```python
from eil import Extractor

extractor = Extractor()
dependencies = extractor.extract_from_file("path/to/your/file.py")
print(dependencies)
```

For example, here are the dependencies extracted from the `extractor.py` file itself:

```python
from eil import Extractor

extractor = Extractor()
dependencies = extractor.extract_from_file("extractor.py")
print(dependencies)
# Output: ['pathlib', 'tree_sitter', 'tree_sitter_language_pack', 'typing']
```

## TODO
- Configure as package and release
- Figure out if I can separate out stdlib vs third-party libraries.