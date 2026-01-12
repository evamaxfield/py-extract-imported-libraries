#!/usr/bin/env python

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from tree_sitter import Language, Parser, Query, QueryCursor
from tree_sitter_language_pack import get_language

from .data import load_stdlibs

###############################################################################


@dataclass
class ImportedLibraries:
    """Container for categorized dependencies."""

    stdlib: set[str]
    third_party: set[str]
    first_party: set[str]


###############################################################################


class Extractor:
    SUPPORTED_LANGUAGES = (
        "python",
        "r",
        # "go",
        # "rust",
        # "javascript",
        # "typescript",
    )

    def __init__(self) -> None:
        self.languages: dict[str, Language] = {}
        self.parsers: dict[str, Parser] = {}
        self.stdlibs = load_stdlibs()

    def _load_language(self: Self, lang: str) -> None:
        """Load a language parser if not already loaded."""
        if lang not in self.parsers:
            try:
                self.languages[lang] = get_language(lang)
                self.parsers[lang] = Parser(self.languages[lang])
            except Exception as e:
                print(f"Warning: Could not load {lang}: {e}")

    def _categorize_libraries(
        self: Self,
        deps: set[str],
        stdlib_set: set[str],
        first_party: set[str] | None = None,
        stdlib_check_func: Callable | None = None,
    ) -> ImportedLibraries:
        """Categorize imports into stdlib, third-party, and first-party."""
        stdlib = set()
        third_party = set()
        first_party_set = first_party or set()

        for dep in deps:
            if stdlib_check_func:
                if stdlib_check_func(dep):
                    stdlib.add(dep)
                else:
                    third_party.add(dep)
            else:
                if dep in stdlib_set:
                    stdlib.add(dep)
                else:
                    third_party.add(dep)

        return ImportedLibraries(
            stdlib=stdlib, third_party=third_party, first_party=first_party_set
        )

    def extract_python_libraries(self: Self, code: str) -> ImportedLibraries:  # noqa: C901
        """Extract imported libraries from Python code."""
        self._load_language("python")
        tree = self.parsers["python"].parse(bytes(code, "utf8"))

        query = Query(
            self.languages["python"],
            """
            (import_statement
              name: (dotted_name) @import)
            
            (import_statement
              name: (aliased_import 
                name: (dotted_name) @import))
            
            (import_from_statement
              module_name: (dotted_name) @import)
            
            (import_from_statement
              module_name: (relative_import) @relative_import)
            """,
        )

        imported_libs = set()
        first_party = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)

        # Handle absolute imports
        for node in captures.get("import", []):
            # Check if this is part of a relative import by examining the parent
            parent = node.parent
            if parent and parent.type == "relative_import":
                # Skip - will be handled in relative imports section
                continue

            dep_name = code[node.start_byte : node.end_byte]
            top_level = dep_name.split(".")[0]
            imported_libs.add(top_level)

        # Handle relative imports (first-party)
        for node in captures.get("relative_import", []):
            # Get the full import statement to extract the module
            import_statement = node.parent
            if import_statement and import_statement.type == "import_from_statement":
                # First check if there's a dotted_name in the relative_import
                has_dotted = False
                for child in node.children:
                    if child.type == "dotted_name":
                        module_text = code[child.start_byte : child.end_byte]
                        top_level = module_text.split(".")[0]
                        first_party.add(top_level)
                        has_dotted = True
                        break

                # If no dotted_name in relative_import, check what's imported
                if not has_dotted:
                    # Look for the name being imported after "import"
                    for child in import_statement.children:
                        if child.type == "dotted_name":
                            # This is after the "import" keyword
                            module_text = code[child.start_byte : child.end_byte]
                            top_level = module_text.split(".")[0]
                            first_party.add(top_level)
                            break
                        elif child.type == "aliased_import":
                            # Handle "from . import utils as u"
                            for subchild in child.children:
                                if subchild.type == "dotted_name":
                                    module_text = code[subchild.start_byte : subchild.end_byte]
                                    top_level = module_text.split(".")[0]
                                    first_party.add(top_level)
                                    break

        return self._categorize_libraries(
            imported_libs, self.stdlibs["python"], first_party=first_party
        )

    def extract_r_libraries(self: Self, code: str) -> ImportedLibraries:  # noqa: C901
        """Extract imported libraries from R code."""
        self._load_language("r")
        tree = self.parsers["r"].parse(bytes(code, "utf8"))

        query = Query(
            self.languages["r"],
            """
            (call
              function: (identifier) @func_name
              arguments: (arguments 
                (argument [(identifier) (string)] @package)))
            
            (namespace_operator
              lhs: (identifier) @package)
            
            (namespace_operator
              lhs: (string) @package)
            """,
        )

        imported_libs = set()
        first_party = set()
        source_arg_positions = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)

        func_nodes = captures.get("func_name", [])
        package_nodes = captures.get("package", [])

        # Sort both lists by position to ensure consistent ordering
        func_nodes_sorted = sorted(func_nodes, key=lambda n: n.start_byte)
        package_nodes_sorted = sorted(package_nodes, key=lambda n: n.start_byte)

        # Handle library(), require(), and source() calls
        for func_node in func_nodes_sorted:
            func_name = code[func_node.start_byte : func_node.end_byte]

            # Find the closest package node that comes after this function node
            # and is within the same call expression (before the next function)
            closest_pkg = None
            min_distance = float("inf")

            for pkg_node in package_nodes_sorted:
                if pkg_node.start_byte > func_node.start_byte:
                    distance = pkg_node.start_byte - func_node.start_byte
                    if distance < min_distance:
                        # Check if there's another function between them
                        has_func_between = any(
                            func_node.start_byte < f.start_byte < pkg_node.start_byte
                            for f in func_nodes_sorted
                        )
                        if not has_func_between:
                            closest_pkg = pkg_node
                            min_distance = distance

            if closest_pkg:
                pkg_text = code[closest_pkg.start_byte : closest_pkg.end_byte]
                pkg_text = pkg_text.strip("\"'")

                if func_name in ("library", "require"):
                    imported_libs.add(pkg_text)
                elif func_name == "source":
                    # Mark this node's position so we skip it later
                    source_arg_positions.add((closest_pkg.start_byte, closest_pkg.end_byte))
                    # Extract the base name without extension
                    base_name = Path(pkg_text).stem
                    if base_name:
                        first_party.add(base_name)

        # Handle :: and ::: operators
        for node in package_nodes_sorted:
            # Skip if this node was part of a source() call
            if (node.start_byte, node.end_byte) in source_arg_positions:
                continue

            pkg_text = code[node.start_byte : node.end_byte]
            pkg_text = pkg_text.strip("\"'")
            # Skip if this looks like a file path (contains / or ends with .R)
            if "/" not in pkg_text and not pkg_text.endswith(".R"):
                imported_libs.add(pkg_text)

        return self._categorize_libraries(
            imported_libs, self.stdlibs["r"], first_party=first_party
        )

    def extract_from_file(self: Self, file_path: str | Path) -> ImportedLibraries:
        """Extract imported libraries from a file based on its extension."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Parse
        code = path.read_text(encoding="utf-8")

        # Map file extensions to extraction methods
        ext_map = {
            ".py": self.extract_python_libraries,
            ".r": self.extract_r_libraries,
            ".R": self.extract_r_libraries,
        }

        # Parse and return or handle unsupported extension
        if path.suffix in ext_map:
            return ext_map[path.suffix](code)

        supported_exts = ", ".join(sorted(set(ext_map.keys())))
        raise ValueError(
            f"Unsupported file extension: {path.suffix}. Supported: {supported_exts}"
        )
