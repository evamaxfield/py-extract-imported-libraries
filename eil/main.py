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


###############################################################################


class Extractor:
    SUPPORTED_LANGUAGES = (
        "python",
        "r",
        "go",
        "rust",
        "javascript",
        "typescript",
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
        stdlib_check_func: Callable | None = None,
    ) -> ImportedLibraries:
        """Categorize i into stdlib and third-party."""
        stdlib = set()
        third_party = set()

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

        return ImportedLibraries(stdlib=stdlib, third_party=third_party)

    def extract_python_libraries(self: Self, code: str) -> ImportedLibraries:
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
              module_name: (relative_import
                (dotted_name) @import))
            """,
        )

        imported_libs = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)

        for node in captures.get("import", []):
            dep_name = code[node.start_byte : node.end_byte]
            top_level = dep_name.split(".")[0]
            imported_libs.add(top_level)

        return self._categorize_libraries(imported_libs, self.stdlibs["python"])

    def extract_r_libraries(self: Self, code: str) -> ImportedLibraries:
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
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)

        func_nodes = captures.get("func_name", [])
        package_nodes = captures.get("package", [])

        for func_node in func_nodes:
            func_name = code[func_node.start_byte : func_node.end_byte]
            if func_name in ("library", "require"):
                for pkg_node in package_nodes:
                    if pkg_node.start_byte > func_node.start_byte:
                        pkg_text = code[pkg_node.start_byte : pkg_node.end_byte]
                        pkg_text = pkg_text.strip("\"'")
                        imported_libs.add(pkg_text)
                        break

        for node in package_nodes:
            pkg_text = code[node.start_byte : node.end_byte]
            pkg_text = pkg_text.strip("\"'")
            imported_libs.add(pkg_text)

        return self._categorize_libraries(imported_libs, self.stdlibs["r"])

    def extract_go_libraries(self: Self, code: str) -> ImportedLibraries:
        """Extract imported libraries from Go code."""
        self._load_language("go")
        tree = self.parsers["go"].parse(bytes(code, "utf8"))

        query = Query(
            self.languages["go"],
            """
            (import_spec
              path: (interpreted_string_literal) @import)
            """,
        )

        imported_libs = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)

        for node in captures.get("import", []):
            import_path = code[node.start_byte : node.end_byte]
            import_path = import_path.strip('"')
            # Keep all imports (both stdlib and third-party)
            imported_libs.add(import_path)

        # Go stdlib check: no dots or slashes means stdlib
        def is_go_stdlib(import_path: str) -> bool:
            return "." not in import_path and "/" not in import_path

        return self._categorize_libraries(imported_libs, set(), stdlib_check_func=is_go_stdlib)

    def extract_rust_libraries(self: Self, code: str) -> ImportedLibraries:
        """Extract imported libraries from Rust code."""
        self._load_language("rust")
        tree = self.parsers["rust"].parse(bytes(code, "utf8"))

        query = Query(
            self.languages["rust"],
            """
            (use_declaration
              argument: (scoped_identifier
                path: (identifier) @crate))
            
            (use_declaration
              argument: (scoped_identifier
                path: (scoped_identifier
                  path: (identifier) @crate)))
            
            (use_declaration
              argument: (identifier) @crate)
            
            (use_declaration
              argument: (scoped_use_list
                path: (identifier) @crate))
            
            (use_declaration
              argument: (scoped_use_list
                path: (scoped_identifier
                  path: (identifier) @crate)))
            """,
        )

        imported_libs = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)

        for node in captures.get("crate", []):
            crate_name = code[node.start_byte : node.end_byte]
            # Don't filter here - we'll categorize everything
            if crate_name not in ("crate", "self", "super"):
                imported_libs.add(crate_name)

        return self._categorize_libraries(imported_libs, self.stdlibs["rust"])

    def extract_javascript_libraries(self: Self, code: str) -> ImportedLibraries:
        """Extract imported libraries from JavaScript code."""
        self._load_language("javascript")
        tree = self.parsers["javascript"].parse(bytes(code, "utf8"))

        query = Query(
            self.languages["javascript"],
            """
            (import_statement
              source: (string) @import)
            
            (call_expression
              function: (identifier) @func
              arguments: (arguments (string) @import))
            """,
        )

        imported_libs = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)

        # Process import statements
        for node in captures.get("import", []):
            import_path = code[node.start_byte : node.end_byte]
            import_path = import_path.strip("\"'")
            # Skip relative imports
            if not import_path.startswith(".") and not import_path.startswith("/"):
                # Extract package name (before any /)
                package = import_path.split("/")[0]
                # Handle scoped packages like @babel/core
                if package.startswith("@") and "/" in import_path:
                    package = "/".join(import_path.split("/")[:2])
                imported_libs.add(package)

        # Also check for require() calls
        func_nodes = captures.get("func", [])
        import_nodes = captures.get("import", [])

        for i, func_node in enumerate(func_nodes):
            func_name = code[func_node.start_byte : func_node.end_byte]
            if func_name == "require" and i < len(import_nodes):
                import_path = code[import_nodes[i].start_byte : import_nodes[i].end_byte]
                import_path = import_path.strip("\"'")
                if not import_path.startswith(".") and not import_path.startswith("/"):
                    package = import_path.split("/")[0]
                    if package.startswith("@") and "/" in import_path:
                        package = "/".join(import_path.split("/")[:2])
                    imported_libs.add(package)

        # Check for node: prefix or in stdlib list
        def is_nodejs_stdlib(package: str) -> bool:
            if package.startswith("node:"):
                return True
            return package in self.stdlibs["javascript"]

        return self._categorize_libraries(
            imported_libs, set(), stdlib_check_func=is_nodejs_stdlib
        )

    def extract_typescript_libraries(self: Self, code: str) -> ImportedLibraries:
        """Extract imported libraries from TypeScript code (similar to JavaScript)."""
        self._load_language("typescript")
        tree = self.parsers["typescript"].parse(bytes(code, "utf8"))

        query = Query(
            self.languages["typescript"],
            """
            (import_statement
              source: (string) @import)
            
            (call_expression
              function: (identifier) @func
              arguments: (arguments (string) @import))
            """,
        )

        imported_libs = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)

        for node in captures.get("import", []):
            import_path = code[node.start_byte : node.end_byte]
            import_path = import_path.strip("\"'")
            if not import_path.startswith(".") and not import_path.startswith("/"):
                package = import_path.split("/")[0]
                if package.startswith("@") and "/" in import_path:
                    package = "/".join(import_path.split("/")[:2])
                imported_libs.add(package)

        def is_nodejs_stdlib(package: str) -> bool:
            if package.startswith("node:"):
                return True
            return package in self.stdlibs["javascript"]

        return self._categorize_libraries(
            imported_libs, set(), stdlib_check_func=is_nodejs_stdlib
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
            ".go": self.extract_go_libraries,
            ".rs": self.extract_rust_libraries,
            ".js": self.extract_javascript_libraries,
            ".jsx": self.extract_javascript_libraries,
            ".ts": self.extract_typescript_libraries,
            ".tsx": self.extract_typescript_libraries,
        }

        # Parse and return or handle unsupported extension
        if path.suffix in ext_map:
            return ext_map[path.suffix](code)

        supported_exts = ", ".join(sorted(set(ext_map.keys())))
        raise ValueError(
            f"Unsupported file extension: {path.suffix}. Supported: {supported_exts}"
        )
