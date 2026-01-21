#!/usr/bin/env python

import traceback
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Self

from tqdm import tqdm
from tree_sitter import Language, Parser, Query, QueryCursor
from tree_sitter_language_pack import SupportedLanguage, get_language

from .data import load_stdlibs

###############################################################################


class ExtractorType(Enum):
    """Enum for selecting which file types to extract from."""

    PYTHON = "python"
    R = "r"
    ALL = "all"


@dataclass
class ImportedLibraries:
    """Container for categorized dependencies."""

    stdlib: set[str]
    third_party: set[str]
    first_party: set[str]


@dataclass
class DirectoryExtractionResult:
    """Result of extracting imports from a directory."""

    extracted: dict[Path, ImportedLibraries] = field(default_factory=dict)
    failed: dict[Path, str] = field(default_factory=dict)


###############################################################################


DEFAULT_IGNORED_DIRS = frozenset(
    {
        "external",
        "ext",
        "vendor",
        "vendors",
        "third_party",
        "third-party",
        "thirdparty",
        "deps",
        "vendor_packages",
    }
)


def _collect_files_to_extract(
    directory: Path,
    extractor_type: ExtractorType,
    recursive: bool = False,
    ignore_dirs: set[str] | None = None,
) -> list[tuple[Path, str]]:
    """Collect all source files in a directory based on extractor type.

    Parameters
    ----------
    directory : Path
        Base directory to search.
    extractor_type : ExtractorType
        Which language types to collect (PYTHON, R, ALL).
    recursive : bool
        Whether to search subdirectories.
    ignore_dirs : set[str] | None
        Directory names to ignore (e.g., 'external', 'vendor'). Matches any
        path part equal to the name.
    """
    files: list[tuple[Path, str]] = []
    glob_pattern = "**/*" if recursive else "*"
    ignore_set = set(ignore_dirs or ())

    def _is_ignored(path: Path) -> bool:
        try:
            rel_parts = path.relative_to(directory).parts
        except Exception:
            rel_parts = path.parts
        return any(part in ignore_set for part in rel_parts)

    def _append_matching(pattern: str, tag: str) -> None:
        for f in directory.glob(pattern):
            if not _is_ignored(f):
                files.append((f, tag))

    if extractor_type in (ExtractorType.PYTHON, ExtractorType.ALL):
        _append_matching(f"{glob_pattern}.py", "python")

    if extractor_type in (ExtractorType.R, ExtractorType.ALL):
        _append_matching(f"{glob_pattern}.r", "r")
        _append_matching(f"{glob_pattern}.R", "r")

    return files


def _collect_ignored_modules(
    directory: Path,
    recursive: bool = False,
    ignore_dirs: set[str] | None = None,
) -> set[str]:
    """Collect module names that live inside ignored directories.

    For directories matching names in `ignore_dirs`, return the immediate
    child directory names and file stems (e.g., `external/utils/__init__.py`
    -> 'utils'). These names will be *ignored* when classifying imports.
    """
    modules: set[str] = set()
    glob_pattern = "**/*" if recursive else "*"
    ignore_set = set(ignore_dirs or ())

    for p in directory.glob(f"{glob_pattern}"):
        if not p.is_dir():
            continue
        # Check if this path is itself an ignored directory
        try:
            rel_parts = p.relative_to(directory).parts
        except Exception:
            rel_parts = p.parts
        if not any(part in ignore_set for part in rel_parts):
            continue

        # If the path itself is an ignored directory (e.g., 'ext', 'vendored'),
        # add its name so top-level imports like `import ext` or
        # `from vendored import foo` are also ignored.
        if p.name in ignore_set:
            modules.add(p.name)

        for child in p.iterdir():
            if child.is_dir():
                modules.add(child.name)
            elif child.is_file():
                modules.add(child.stem)

    return modules


def _collect_repository_modules(
    directory: Path,
    recursive: bool = False,
    ignore_dirs: set[str] | None = None,
) -> set[str]:
    """
    Collect module names from source files and package directories in a directory.

    Returns a set of names that could match top-level imports: file stems of
    Python and R files, and directory names that contain source files
    (e.g., packages with __init__.py or directories with .R files).

    Parameters
    ----------
    directory : Path
        Base directory to search.
    recursive : bool
        Whether to search subdirectories.
    ignore_dirs : set[str] | None
        Directory names to ignore.
    """
    modules: set[str] = set()
    glob_pattern = "**/*" if recursive else "*"
    ignore_set = set(ignore_dirs or ())

    def _is_ignored(path: Path) -> bool:
        try:
            rel_parts = path.relative_to(directory).parts
        except Exception:
            rel_parts = path.parts
        return any(part in ignore_set for part in rel_parts)

    def _add_file_stems(pattern: str) -> None:
        for file_path in directory.glob(pattern):
            if not _is_ignored(file_path):
                modules.add(file_path.stem)

    # Collect Python modules (file stems)
    _add_file_stems(f"{glob_pattern}.py")

    # Collect R modules (file stems)
    _add_file_stems(f"{glob_pattern}.r")
    _add_file_stems(f"{glob_pattern}.R")

    # Collect package/directory names that contain source files
    for p in directory.glob(f"{glob_pattern}"):
        if p.is_dir() and not _is_ignored(p):
            has_py = any(p.glob("*.py"))
            has_r = any(p.glob("*.r")) or any(p.glob("*.R"))
            if has_py or has_r:
                modules.add(p.name)

    return modules


class Extractor:
    SUPPORTED_LANGUAGES = (
        "python",
        "r",
        # "go",
        # "rust",
        # "javascript",
        # "typescript",
    )

    _PYTHON_QUERY = """
        (import_statement
          name: (dotted_name) @import)

        (import_statement
          name: (aliased_import
            name: (dotted_name) @import))

        (import_from_statement
          module_name: (dotted_name) @import)

        (import_from_statement
          module_name: (relative_import) @relative_import)
        """

    _R_QUERY = """
        (call
          function: (identifier) @func_name
          arguments: (arguments
            (argument [(identifier) (string)] @package)))

        (namespace_operator
          lhs: (identifier) @package)

        (namespace_operator
          lhs: (string) @package)
        """

    def __init__(self) -> None:
        self.languages: dict[SupportedLanguage, Language] = {}
        self.parsers: dict[SupportedLanguage, Parser] = {}
        self.queries: dict[SupportedLanguage, Query] = {}
        self.stdlibs = load_stdlibs()

    def _load_language(self: Self, lang: SupportedLanguage) -> None:
        """Load a language parser and query if not already loaded."""
        if lang not in self.parsers:
            self.languages[lang] = get_language(lang)
            self.parsers[lang] = Parser(self.languages[lang])

            # Cache the query for this language
            query_map: dict[SupportedLanguage, str] = {
                "python": self._PYTHON_QUERY,
                "r": self._R_QUERY,
            }
            if lang in query_map:
                self.queries[lang] = Query(self.languages[lang], query_map[lang])

    def _categorize_libraries(
        self: Self,
        deps: set[str],
        stdlib_set: set[str],
        first_party: set[str] | None = None,
        stdlib_check_func: Callable[[str], bool] | None = None,
        repo_files: set[str] | None = None,
        ignored_modules: set[str] | None = None,
        language: str | None = None,
    ) -> ImportedLibraries:
        """Categorize imports into stdlib, third-party, and first-party.

        Any name in `ignored_modules` will be skipped entirely (not added to
        third_party or first_party) — this is used to ignore vendored code.

        A language may be provided to apply language-specific package-name
        validation rules; invalid names are dropped from the resulting sets.
        """
        stdlib: set[str] = set()
        third_party: set[str] = set()
        first_party_set = first_party or set()
        repo_files_set = repo_files or set()
        ignored_set = ignored_modules or set()

        for dep in deps:
            # Skip if this dependency lives in an ignored directory
            if dep in ignored_set:
                continue

            # Skip if already identified as first-party
            if dep in first_party_set:
                continue

            # First-party project files take precedence
            if dep in repo_files_set:
                first_party_set.add(dep)
                continue

            if stdlib_check_func:
                if stdlib_check_func(dep):
                    stdlib.add(dep)
                else:
                    third_party.add(dep)
            elif dep in stdlib_set:
                stdlib.add(dep)
            else:
                third_party.add(dep)

        # Language-specific validation helpers
        def _is_valid_python_import(name: str) -> bool:
            # Python imports are Python identifiers (module/package names used in
            # import statements) and must start with a letter or underscore and
            # only contain letters, digits, or underscores.
            return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name))

        def _is_valid_r_package(name: str) -> bool:
            # CRAN package names typically start with a letter and may contain
            # letters, digits and dots. Be conservative: require starting letter
            # and only allow letters, digits and dots.
            return bool(re.match(r"^[A-Za-z][A-Za-z0-9.]*$", name))

        def _is_valid_r_first_party(name: str) -> bool:
            # First-party R file stems may contain underscores and hyphens; allow
            # letters, digits, underscores, dots and hyphens but require a
            # starting letter or underscore.
            return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_.-]*$", name))

        def _filter_names(names: set[str], lang: str | None, category: str = "third") -> set[str]:
            if lang == "python":
                fn = _is_valid_python_import
            elif lang == "r":
                fn = _is_valid_r_first_party if category == "first" else _is_valid_r_package
            else:
                return set(names)
            return {n for n in names if fn(n)}

        stdlib = _filter_names(stdlib, language, category="stdlib")
        third_party = _filter_names(third_party, language, category="third")
        first_party_set = _filter_names(first_party_set, language, category="first")

        return ImportedLibraries(
            stdlib=stdlib, third_party=third_party, first_party=first_party_set
        )

    def _python_absolute_imports(self, captures: dict, code: str) -> set[str]:
        """Return top-level names from absolute import captures."""
        libs: set[str] = set()
        for node in captures.get("import", []):
            parent = node.parent
            if parent and parent.type == "relative_import":
                continue
            dep_name = code[node.start_byte : node.end_byte]
            libs.add(dep_name.split(".")[0])
        return libs

    def _python_extract_from_import_statement(self, import_statement, code: str) -> str | None:
        """Check an import_from_statement and return the top-level module if present."""
        for child in import_statement.children:
            if child.type == "dotted_name":
                return code[child.start_byte : child.end_byte].split(".")[0]
            if child.type == "aliased_import":
                for subchild in child.children:
                    if subchild.type == "dotted_name":
                        return code[subchild.start_byte : subchild.end_byte].split(".")[0]
        return None

    def _python_relative_dotted_name(self, node, code: str) -> str | None:
        """Return top-level name from a dotted_name child in a relative import node."""
        for child in node.children:
            if child.type == "dotted_name":
                return code[child.start_byte : child.end_byte].split(".")[0]
        return None

    def _python_relative_imports(self, captures: dict, code: str) -> set[str]:
        """Return module names from relative import captures (first-party)."""
        first_party: set[str] = set()
        for node in captures.get("relative_import", []):
            import_statement = node.parent
            if not import_statement or import_statement.type != "import_from_statement":
                continue

            dotted = self._python_relative_dotted_name(node, code)
            if dotted:
                first_party.add(dotted)
                continue

            # Fallback: use helper to get the imported module from the import statement
            module = self._python_extract_from_import_statement(import_statement, code)
            if module:
                first_party.add(module)
        return first_party

    def extract_python_libraries(
        self: Self,
        code: str,
        repo_files: set[str] | None = None,
        ignored_modules: set[str] | None = None,
    ) -> ImportedLibraries:
        """Extract imported libraries from Python code."""
        self._load_language("python")
        tree = self.parsers["python"].parse(bytes(code, "utf8"))

        query_cursor = QueryCursor(self.queries["python"])
        captures = query_cursor.captures(tree.root_node)

        imported_libs = self._python_absolute_imports(captures, code)
        first_party = self._python_relative_imports(captures, code)

        return self._categorize_libraries(
            imported_libs,
            self.stdlibs["python"],
            first_party=first_party,
            repo_files=repo_files,
            ignored_modules=ignored_modules,
            language="python",
        )

    def _r_process_calls(
        self, captures: dict, code: str
    ) -> tuple[set[str], set[str], set[tuple[int, int]]]:
        """Process library/require/source calls and return imports and source positions."""
        imported_libs: set[str] = set()
        first_party: set[str] = set()
        source_arg_positions: set[tuple[int, int]] = set()

        func_nodes = captures.get("func_name", [])
        package_nodes = captures.get("package", [])
        func_nodes_sorted = sorted(func_nodes, key=lambda n: n.start_byte)
        package_nodes_sorted = sorted(package_nodes, key=lambda n: n.start_byte)

        for func_node in func_nodes_sorted:
            func_name = code[func_node.start_byte : func_node.end_byte]

            # Only consider known import/source functions
            if func_name not in ("library", "require", "source"):
                continue

            # Find the enclosing call node for this function
            call_node = func_node.parent
            while call_node and call_node.type != "call":
                call_node = call_node.parent
            if not call_node:
                continue

            # Helper: is `node` a descendant of `ancestor`?
            def _is_descendant(node, ancestor):
                cur = node.parent
                while cur:
                    if cur == ancestor:
                        return True
                    cur = cur.parent
                return False

            # Collect package nodes that are part of the same call
            candidate_pkgs = [
                p
                for p in package_nodes_sorted
                if p.start_byte > func_node.start_byte and _is_descendant(p, call_node)
            ]

            if not candidate_pkgs:
                continue

            # Prefer the first candidate that is not the name of a named argument
            chosen_pkg = None
            for pkg_node in candidate_pkgs:
                pos = pkg_node.end_byte
                while pos < len(code) and code[pos].isspace():
                    pos += 1
                if pos < len(code) and code[pos] == "=":
                    # This is the argument name (e.g., `package =` or `family =`),
                    # skip it in favor of the next candidate (likely the value).
                    continue
                chosen_pkg = pkg_node
                break

            # If we didn't find a non-named-arg candidate, prefer a string literal
            if not chosen_pkg:
                for pkg_node in candidate_pkgs:
                    text = code[pkg_node.start_byte : pkg_node.end_byte].strip()
                    if text.startswith('"') or text.startswith("'"):
                        chosen_pkg = pkg_node
                        break

            if not chosen_pkg:
                continue

            pkg_text = code[chosen_pkg.start_byte : chosen_pkg.end_byte].strip("\"'")

            if func_name in ("library", "require"):
                imported_libs.add(pkg_text)
            elif func_name == "source":
                source_arg_positions.add((chosen_pkg.start_byte, chosen_pkg.end_byte))
                base_name = Path(pkg_text).stem
                if base_name:
                    first_party.add(base_name)

        return imported_libs, first_party, source_arg_positions

    def _r_process_namespace_ops(
        self, captures: dict, code: str, source_arg_positions: set[tuple[int, int]]
    ) -> set[str]:
        """Process :: and ::: namespace operators to extract package names."""
        imported_libs: set[str] = set()
        package_nodes = captures.get("package", [])
        package_nodes_sorted = sorted(package_nodes, key=lambda n: n.start_byte)

        for node in package_nodes_sorted:
            # Only consider nodes that are part of a namespace operator (lhs of :: or :::)
            if not node.parent or node.parent.type != "namespace_operator":
                continue

            if (node.start_byte, node.end_byte) in source_arg_positions:
                continue

            pkg_text = code[node.start_byte : node.end_byte].strip("\"'")
            if "/" not in pkg_text and not pkg_text.endswith(".R"):
                imported_libs.add(pkg_text)
        return imported_libs

    def extract_r_libraries(
        self: Self,
        code: str,
        repo_files: set[str] | None = None,
        ignored_modules: set[str] | None = None,
    ) -> ImportedLibraries:
        """Extract imported libraries from R code."""
        self._load_language("r")
        tree = self.parsers["r"].parse(bytes(code, "utf8"))

        query_cursor = QueryCursor(self.queries["r"])
        captures = query_cursor.captures(tree.root_node)

        imported_from_calls, first_party, source_arg_positions = self._r_process_calls(
            captures, code
        )
        imported_from_namespace = self._r_process_namespace_ops(
            captures, code, source_arg_positions
        )

        imported_libs = imported_from_calls.union(imported_from_namespace)

        return self._categorize_libraries(
            imported_libs,
            self.stdlibs["r"],
            first_party=first_party,
            repo_files=repo_files,
            ignored_modules=ignored_modules,
            language="r",
        )

    def extract_from_file(
        self: Self,
        file_path: str | Path,
        repo_files: set[str] | None = None,
        ignored_modules: set[str] | None = None,
    ) -> ImportedLibraries:
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
            return ext_map[path.suffix](
                code,
                repo_files=repo_files,
                ignored_modules=ignored_modules,
            )

        supported_exts = ", ".join(sorted(set(ext_map.keys())))
        raise ValueError(
            f"Unsupported file extension: {path.suffix}. Supported: {supported_exts}"
        )

    def extract_from_directory(
        self: Self,
        directory: str | Path,
        extractor_type: ExtractorType = ExtractorType.ALL,
        recursive: bool = False,
        show_progress: bool = True,
        progress_leave: bool = True,
        ignore_directories_list: set[str] | None = None,
    ) -> DirectoryExtractionResult:
        """
        Extract imported libraries from all source files in a directory.

        Parameters
        ----------
        directory : str | Path
            Path to the directory containing source files.
        extractor_type : ExtractorType
            Which file types to extract from: PYTHON (only .py files),
            R (only .r/.R files), or ALL (default, extracts from all supported types).
        recursive : bool
            Whether to search recursively in subdirectories (default False).
        show_progress : bool
            Whether to display a progress bar (default True).
        progress_leave : bool
            Whether to leave the progress bar visible after completion (default True).
            Set to False to remove the progress bar when done.
        ignore_directories_list : set[str] | None
            Directory names to ignore when classifying first-party modules. If
            None, a default set of common names (e.g., 'external', 'vendor')
            will be used.

        Returns
        -------
        DirectoryExtractionResult
            Dataclass containing successfully extracted files and failed extractions
            with their tracebacks.

        Raises
        ------
        NotADirectoryError
            If the provided path is not a directory.
        """
        directory = Path(directory).resolve()
        if not directory.is_dir():
            raise NotADirectoryError(f"{directory} is not a directory")

        # Build ignore list defaulting to common names for vendored/copied code
        if ignore_directories_list is None:
            ignore_set = set(DEFAULT_IGNORED_DIRS)
        else:
            ignore_set = set(ignore_directories_list)

        files_to_extract = _collect_files_to_extract(
            directory, extractor_type, recursive, ignore_dirs=ignore_set
        )
        repo_files = _collect_repository_modules(directory, recursive, ignore_dirs=ignore_set)

        result = DirectoryExtractionResult()
        if not files_to_extract:
            return result

        progress_bar = tqdm(
            files_to_extract,
            desc="Extracting imports",
            leave=progress_leave,
            disable=not show_progress,
        )

        # Collect module names that live in ignored directories so we can exclude
        # imports that reference vendored code entirely.
        ignored_modules = _collect_ignored_modules(directory, recursive, ignore_set)

        for file_path, _file_type in progress_bar:
            progress_bar.set_description(f"Extracting {file_path.name}")
            try:
                result.extracted[file_path] = self.extract_from_file(
                    file_path,
                    repo_files=repo_files,
                    ignored_modules=ignored_modules,
                )
            except Exception:
                result.failed[file_path] = traceback.format_exc()

        return result
