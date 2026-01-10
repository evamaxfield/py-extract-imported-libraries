from pathlib import Path
from typing import Set, Self

from tree_sitter import Parser, Query, QueryCursor
from tree_sitter_language_pack import get_language

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
        self.languages = {}
        self.parsers = {}

    def _load_language(self: Self, lang: str) -> None:
        """Load a language parser if not already loaded."""
        if lang not in self.parsers:
            try:
                self.languages[lang] = get_language(lang)
                self.parsers[lang] = Parser(self.languages[lang])
            except Exception as e:
                print(f"Warning: Could not load {lang}: {e}")


    def extract_python_dependencies(self: Self, code: str) -> Set[str]:
        """Extract dependencies from Python code."""
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
            """
        )
        
        dependencies = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)
        
        for node in captures.get("import", []):
            dep_name = code[node.start_byte:node.end_byte]
            top_level = dep_name.split('.')[0]
            dependencies.add(top_level)
        
        return dependencies
    
    def extract_r_dependencies(self: Self, code: str) -> Set[str]:
        """Extract dependencies from R code."""
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
            """
        )
        
        dependencies = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)
        
        func_nodes = captures.get("func_name", [])
        package_nodes = captures.get("package", [])
        
        for func_node in func_nodes:
            func_name = code[func_node.start_byte:func_node.end_byte]
            if func_name in ("library", "require"):
                for pkg_node in package_nodes:
                    if pkg_node.start_byte > func_node.start_byte:
                        pkg_text = code[pkg_node.start_byte:pkg_node.end_byte]
                        pkg_text = pkg_text.strip('"\'')
                        dependencies.add(pkg_text)
                        break
        
        for node in package_nodes:
            pkg_text = code[node.start_byte:node.end_byte]
            pkg_text = pkg_text.strip('"\'')
            dependencies.add(pkg_text)
        
        return dependencies
    
    def extract_go_dependencies(self: Self, code: str) -> Set[str]:
        """Extract dependencies from Go code."""
        self._load_language("go")
        tree = self.parsers["go"].parse(bytes(code, "utf8"))
        
        query = Query(
            self.languages["go"],
            """
            (import_spec
              path: (interpreted_string_literal) @import)
            """
        )
        
        dependencies = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)
        
        for node in captures.get("import", []):
            import_path = code[node.start_byte:node.end_byte]
            # Remove quotes
            import_path = import_path.strip('"')
            # Filter out standard library imports (no dots in path typically)
            # Keep third-party packages (usually have domain names like github.com)
            if '.' in import_path or '/' in import_path:
                dependencies.add(import_path)
        
        return dependencies
    
    def extract_rust_dependencies(self: Self, code: str) -> Set[str]:
        """Extract dependencies from Rust code."""
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
            """
        )
        
        dependencies = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)
        
        for node in captures.get("crate", []):
            crate_name = code[node.start_byte:node.end_byte]
            # Filter out std library and common keywords
            if crate_name not in ("std", "core", "alloc", "crate", "self", "super"):
                dependencies.add(crate_name)
        
        return dependencies
    
    def extract_javascript_dependencies(self: Self, code: str) -> Set[str]:
        """Extract dependencies from JavaScript code."""
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
            """
        )
        
        dependencies = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)
        
        # Process import statements
        for node in captures.get("import", []):
            import_path = code[node.start_byte:node.end_byte]
            import_path = import_path.strip('"\'')
            # Skip relative imports
            if not import_path.startswith('.') and not import_path.startswith('/'):
                # Extract package name (before any /)
                package = import_path.split('/')[0]
                # Handle scoped packages like @babel/core
                if package.startswith('@') and '/' in import_path:
                    package = '/'.join(import_path.split('/')[:2])
                dependencies.add(package)
        
        # Also check for require() calls
        func_nodes = captures.get("func", [])
        import_nodes = captures.get("import", [])
        
        for i, func_node in enumerate(func_nodes):
            func_name = code[func_node.start_byte:func_node.end_byte]
            if func_name == "require" and i < len(import_nodes):
                import_path = code[import_nodes[i].start_byte:import_nodes[i].end_byte]
                import_path = import_path.strip('"\'')
                if not import_path.startswith('.') and not import_path.startswith('/'):
                    package = import_path.split('/')[0]
                    if package.startswith('@') and '/' in import_path:
                        package = '/'.join(import_path.split('/')[:2])
                    dependencies.add(package)
        
        return dependencies
    
    def extract_typescript_dependencies(self: Self, code: str) -> Set[str]:
        """Extract dependencies from TypeScript code (similar to JavaScript)."""
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
            """
        )
        
        dependencies = set()
        query_cursor = QueryCursor(query)
        captures = query_cursor.captures(tree.root_node)
        
        for node in captures.get("import", []):
            import_path = code[node.start_byte:node.end_byte]
            import_path = import_path.strip('"\'')
            if not import_path.startswith('.') and not import_path.startswith('/'):
                package = import_path.split('/')[0]
                if package.startswith('@') and '/' in import_path:
                    package = '/'.join(import_path.split('/')[:2])
                dependencies.add(package)
        
        return dependencies
    
    def extract_from_file(self: Self, file_path: str) -> Set[str]:
        """Extract dependencies from a file based on its extension."""
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        code = path.read_text(encoding='utf-8')
        
        # Map file extensions to extraction methods
        ext_map = {
            '.py': self.extract_python_dependencies,
            '.r': self.extract_r_dependencies,
            '.R': self.extract_r_dependencies,
            '.go': self.extract_go_dependencies,
            '.rs': self.extract_rust_dependencies,
            '.js': self.extract_javascript_dependencies,
            '.jsx': self.extract_javascript_dependencies,
            '.ts': self.extract_typescript_dependencies,
            '.tsx': self.extract_typescript_dependencies,
        }
        
        if path.suffix in ext_map:
            return ext_map[path.suffix](code)
        else:
            supported_exts = ', '.join(sorted(set(ext_map.keys())))
            raise ValueError(f"Unsupported file extension: {path.suffix}. Supported: {supported_exts}")