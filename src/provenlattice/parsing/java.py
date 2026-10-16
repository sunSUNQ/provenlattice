from __future__ import annotations

from bisect import bisect_right
from typing import Any

from ..models import ParsedFile, ParsedImport, ParsedReference, ParsedSymbol
from .base import ParseOutcome

try:  # Keep the Python-only installation usable until the Java grammar is installed.
    import tree_sitter_java
    from tree_sitter import Language, Parser
except ImportError:  # pragma: no cover
    tree_sitter_java = None
    Language = Parser = None


def module_name(relative_path: str) -> str:
    parts = relative_path.replace("\\", "/").split("/")
    parts[-1] = parts[-1].rsplit(".", 1)[0]
    return ".".join(parts)


_TYPE_KINDS = {
    "class_declaration": ("Class", "class"),
    "interface_declaration": ("Interface", "interface"),
    "enum_declaration": ("Class", "enum"),
    "record_declaration": ("Class", "record"),
    "annotation_type_declaration": ("Interface", "annotation"),
}
_METHOD_NODES = {"method_declaration", "constructor_declaration", "compact_constructor_declaration"}
_IDENTIFIER_CHAIN_NODES = {"generic_type", "scoped_type_identifier"}


class JavaTreeSitterParser:
    """Tree-sitter adapter for Java sources (parsing/base.py ParserAdapter contract)."""

    language = "java"
    extensions = frozenset({".java"})

    def __init__(self) -> None:
        if Language is None or tree_sitter_java is None:
            raise RuntimeError(
                "The tree-sitter-java grammar is not installed; Java parsing is unavailable."
            )
        self._parser = Parser(Language(tree_sitter_java.language()))

    def parse(self, path: Any, relative_path: str) -> ParsedFile:
        return self.parse_bytes(path.read_bytes(), relative_path).parsed

    def parse_bytes(self, source: bytes, relative_path: str, old_tree: Any | None = None) -> ParseOutcome:
        tree = self._parser.parse(source) if old_tree is None else self._parser.parse(source, old_tree)
        changed_ranges: list[dict] = []
        if old_tree is not None:
            changed_ranges = [
                {
                    "start_byte": span.start_byte,
                    "end_byte": span.end_byte,
                    "start_point": list(span.start_point),
                    "end_point": list(span.end_point),
                }
                for span in old_tree.changed_ranges(tree)
            ]
        parsed = JavaExtractor(source, relative_path).extract(tree.root_node)
        return ParseOutcome(parsed, tree, changed_ranges)


class JavaExtractor:
    """Normalize the conservative, syntax-only Java Tree-sitter facts.

    Member kinds reuse the frozen schema (D1): classes/interfaces/enums/
    records/annotations map to Class/Interface with a ``java_kind`` marker,
    fields/constructors/enum constants map to Method with a ``java_member``
    marker. Ambiguous or unbindable shapes are emitted as conservative
    candidate facts; nothing here fabricates a resolved target.
    """

    def __init__(self, source: bytes, relative_path: str) -> None:
        self.source = source
        self.line_starts = [0, *(index + 1 for index, value in enumerate(source) if value == 10)]
        self.module = module_name(relative_path)
        self.package = ""
        self.scope: list[tuple[str, str]] = []
        self.symbols: list[ParsedSymbol] = []
        self.references: list[ParsedReference] = []
        self.imports: list[ParsedImport] = []
        self.import_aliases: dict[str, tuple[str, str | None]] = {}
        self.type_aliases: set[str] = set()
        self.static_member_aliases: set[str] = set()
        self.declared_types: set[str] = set()
        self.locals: set[str] = set()

    def text(self, node: Any | None) -> str:
        if node is None:
            return ""
        return self.source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def qualified(self, name: str | None = None) -> str:
        base = self.package or self.module
        return ".".join(
            part for part in [base, *(item[0] for item in self.scope), name] if part
        )

    def current_symbol(self) -> str:
        return self.qualified()

    def line(self, node: Any, *, end: bool = False) -> int:
        return bisect_right(self.line_starts, node.end_byte if end else node.start_byte)

    @staticmethod
    def _same_node(left: Any | None, right: Any | None) -> bool:
        return (
            left is not None and right is not None
            and left.type == right.type
            and left.start_byte == right.start_byte
            and left.end_byte == right.end_byte
        )

    def extract(self, root: Any) -> ParsedFile:
        self._collect_declared_types(root)
        self._walk(root)
        return ParsedFile(self.symbols, self.references, self.imports, parser="tree-sitter-java")

    # -- two-phase helpers -------------------------------------------------

    def _collect_declared_types(self, node: Any) -> None:
        if node.type in _TYPE_KINDS:
            name = self.text(node.child_by_field_name("name"))
            if name:
                self.declared_types.add(name)
        for child in node.named_children:
            self._collect_declared_types(child)

    def _walk(self, node: Any) -> None:
        ntype = node.type
        if ntype == "package_declaration":
            for child in node.named_children:
                if child.type in {"scoped_identifier", "identifier"}:
                    self.package = self.text(child)
            return
        if ntype == "import_declaration":
            self._import(node)
            return
        if ntype in _TYPE_KINDS:
            self._type_declaration(node)
            return
        if ntype in _METHOD_NODES:
            self._method(node)
            return
        if ntype == "field_declaration":
            self._field(node)
            return
        if ntype == "enum_constant":
            self._enum_constant(node)
            return
        if ntype == "method_invocation":
            self._call(node)
            self._walk_children(node, {"name"})
            return
        if ntype == "object_creation_expression":
            self._new(node)
            return
        if ntype == "explicit_constructor_invocation":
            self._explicit_ctor(node)
            return
        if ntype == "method_reference":
            self._method_ref(node)
            return
        if ntype in {"annotation", "marker_annotation"}:
            self._annotation_usage(node)
            return
        if ntype in _IDENTIFIER_CHAIN_NODES:
            self._chained_type(node)
            for child in node.named_children:
                self._walk(child)
            return
        if ntype == "field_access":
            self._field_access(node)
            return
        if ntype == "local_variable_declaration":
            for declarator in node.named_children:
                if declarator.type == "variable_declarator":
                    self._add_local(declarator.child_by_field_name("name"))
            for child in node.named_children:
                self._walk(child)
            return
        if ntype == "enhanced_for_statement":
            self._add_local(node.child_by_field_name("name"))
            for child in node.named_children:
                self._walk(child)
            return
        if ntype == "resource":
            for child in node.named_children:
                if child.type == "variable_declarator":
                    self._add_local(child.child_by_field_name("name"))
            for child in node.named_children:
                self._walk(child)
            return
        if ntype == "catch_formal_parameter":
            self._add_local(node.child_by_field_name("name"))
            for child in node.named_children:
                self._walk(child)
            return
        if ntype == "lambda_expression":
            self._add_lambda_params(node.child_by_field_name("parameters"))
            for child in node.named_children:
                self._walk(child)
            return
        if ntype == "type_pattern":
            named = node.named_children
            if named:
                self._add_local(named[-1])
            for child in named:
                self._walk(child)
            return
        if ntype == "instanceof_expression":
            self._add_local(node.child_by_field_name("name"))
            for child in node.named_children:
                self._walk(child)
            return
        if ntype == "type_identifier":
            self._type_reference(node)
            return
        if ntype == "identifier":
            self._identifier_reference(node)
            return
        for child in node.named_children:
            self._walk(child)

    def _walk_children(self, node: Any, skip_fields: set[str]) -> None:
        skipped = [node.child_by_field_name(field) for field in skip_fields]
        for child in node.named_children:
            if any(self._same_node(child, skip) for skip in skipped):
                continue
            self._walk(child)

    # -- declarations ------------------------------------------------------

    def _modifiers(self, node: Any) -> tuple[str, bool, bool]:
        visibility, static = "package", False
        modifiers = next((child for child in node.children if child.type == "modifiers"), None)
        if modifiers is not None:
            for child in modifiers.children:
                if child.type in {"public", "protected", "private"}:
                    visibility = child.type
                elif child.type == "static":
                    static = True
        return visibility, static, visibility in {"public", "protected"}

    def _type_declaration(self, node: Any) -> None:
        kind, java_kind = _TYPE_KINDS[node.type]
        name = self.text(node.child_by_field_name("name"))
        if not name:
            return
        qualified = self.qualified(name)
        visibility, static, public = self._modifiers(node)
        self.symbols.append(
            ParsedSymbol(
                kind, name, qualified, self.line(node), self.line(node, end=True),
                "", public,
                {"java_kind": java_kind, "visibility": visibility, "static": static,
                 "definition": True},
            )
        )
        for base_text, relation in self._bases(node):
            target, module = self._rewrite(base_text)
            self._ref(
                target, ref_type="IMPLEMENTS", target_module=module, owner=qualified,
                metadata={"java_relation": relation, "syntax": "inheritance"}, node=node,
            )
        self.scope.append((name, kind))
        body = node.child_by_field_name("body")
        if body is not None:
            self._walk(body)
        self.scope.pop()

    def _bases(self, node: Any) -> list[tuple[str, str]]:
        bases: list[tuple[str, str]] = []
        superclass = node.child_by_field_name("superclass")
        if superclass is not None and superclass.named_children:
            base_text = self._base_text(superclass.named_children[-1])
            if base_text:
                bases.append((base_text, "extends"))
        for field_name, relation in (("interfaces", "implements"), ("extends_interfaces", "extends")):
            wrapper = node.child_by_field_name(field_name)
            if wrapper is None:
                continue
            for child in wrapper.named_children:
                if child.type != "type_list":
                    continue
                for item in child.named_children:
                    base_text = self._base_text(item)
                    if base_text:
                        bases.append((base_text, relation))
        return bases

    def _method(self, node: Any) -> None:
        name = self.text(node.child_by_field_name("name"))
        if not name:
            return
        visibility, static, public = self._modifiers(node)
        param_types: list[str] = []
        param_names: list[str] = []
        parameters = node.child_by_field_name("parameters")
        param_type_nodes: list[Any] = []
        if parameters is not None:
            for child in parameters.named_children:
                if child.type == "formal_parameter":
                    type_node = child.child_by_field_name("type")
                    param_type_nodes.append(type_node)
                    param_types.append(self.text(type_node))
                    param_names.append(self.text(child.child_by_field_name("name")))
                elif child.type == "spread_parameter":
                    named = child.named_children
                    param_type_nodes.append(named[0] if named else None)
                    param_types.append(self.text(named[0]) + "..." if named else "")
                    if len(named) > 1:
                        param_names.append(self.text(named[-1].child_by_field_name("name")))
        is_ctor = node.type in {"constructor_declaration", "compact_constructor_declaration"}
        signature = f"({', '.join(param_types)})"
        return_type_node = None
        if not is_ctor:
            return_type_node = node.child_by_field_name("type")
            return_type = self.text(return_type_node)
            signature = f"{signature} -> {return_type}"
        self.symbols.append(
            ParsedSymbol(
                "Method", name, self.qualified(name), self.line(node), self.line(node, end=True),
                signature, public,
                {"java_member": "constructor" if is_ctor else "method",
                 "static": static, "visibility": visibility, "definition": True},
            )
        )
        self.scope.append((name, "Method"))
        self.locals.update(item for item in param_names if item)
        for type_node in [*param_type_nodes, return_type_node]:
            if type_node is not None:
                self._walk(type_node)
        body = node.child_by_field_name("body")
        if body is not None:
            self._walk(body)
        self.scope.pop()
        self.locals.clear()

    def _field(self, node: Any) -> None:
        type_node = node.child_by_field_name("type")
        type_text = self.text(type_node)
        visibility, static, public = self._modifiers(node)
        for declarator in node.named_children:
            if declarator.type != "variable_declarator":
                continue
            name = self.text(declarator.child_by_field_name("name"))
            if not name:
                continue
            self.symbols.append(
                ParsedSymbol(
                    "Method", name, self.qualified(name), self.line(declarator),
                    self.line(declarator, end=True), f"{type_text} {name}".strip(), public,
                    {"java_member": "field", "static": static, "visibility": visibility,
                     "definition": True},
                )
            )
            if type_node is not None:
                self._walk(type_node)
            value = declarator.child_by_field_name("value")
            if value is not None:
                self._walk(value)

    def _enum_constant(self, node: Any) -> None:
        name = self.text(node.child_by_field_name("name"))
        if not name:
            return
        visibility, _static, public = self._modifiers(node)
        owner = self._innermost_type_name()
        self.symbols.append(
            ParsedSymbol(
                "Method", name, self.qualified(name), self.line(node), self.line(node, end=True),
                f"{owner} {name}".strip(), public,
                {"java_member": "enum_constant", "visibility": visibility, "definition": True},
            )
        )
        arguments = node.child_by_field_name("arguments")
        if arguments is not None:
            self._walk(arguments)

    def _import(self, node: Any) -> None:
        body = self.text(node).strip()
        if body.startswith("import"):
            body = body[len("import"):]
        if body.endswith(";"):
            body = body[:-1]
        body = body.strip()
        is_static = body.startswith("static")
        if is_static:
            body = body[len("static"):].strip()
        wildcard = body.endswith(".*")
        if wildcard:
            body = body[:-2]
        if not body:
            return
        if wildcard:
            module, target = body, "*"
        else:
            module, _, target = body.rpartition(".")
        if not target:
            return
        self.imports.append(
            ParsedImport(
                self.module, target, module, None,
                {"start_line": self.line(node), "end_line": self.line(node, end=True),
                 "static": is_static, "wildcard": wildcard},
            )
        )
        if not wildcard:
            self.import_aliases[target] = (module, target)
            if is_static:
                self.static_member_aliases.add(target)
            else:
                self.type_aliases.add(target)

    # -- references and calls ---------------------------------------------

    def _ref(
        self, target: str, *, ref_type: str = "REFERENCES", target_module: str | None = None,
        metadata: dict | None = None, node: Any | None = None, owner: str | None = None,
    ) -> None:
        source_name = owner if owner is not None else self.current_symbol()
        if not source_name or not target:
            return
        self.references.append(
            ParsedReference(
                source_name, ref_type, target, target_module,
                metadata=metadata or {},
                start_line=self.line(node) if node is not None else None,
                end_line=self.line(node, end=True) if node is not None else None,
            )
        )

    def _rewrite(self, target: str) -> tuple[str, str | None]:
        # Mirrors parsing/python.py: the alias table keeps (module, local
        # target); the resolver's import ladder joins module + target, so the
        # rewritten target stays as written and only the module is attached.
        root, _, suffix = target.partition(".")
        imported = self.import_aliases.get(root)
        if imported:
            module, imported_name = imported
            if imported_name:
                return imported_name + (f".{suffix}" if suffix else ""), module
            if suffix:
                return suffix, module
        return target, None

    def _base_text(self, node: Any) -> str:
        return self.text(node).split("<", 1)[0].strip()

    def _receiver_shape(self, object_node: Any, receiver: str) -> str:
        """Classify the receiver of a method invocation for P2-A R1 demotion.

        "identifier" = a plain variable/field/parameter or a static-imported
        member constant: the declared type is NOT statically known from the
        syntax-only view, so name-only bindings are unsafe (P2-A R1).
        "class_static" = the receiver root names an in-file or imported class
        (single-type import), which is explicit evidence.
        """
        if object_node is None:
            return "implicit_this"
        if object_node.type == "this":
            return "this"
        if receiver == "super" or object_node.type == "super":
            return "super"
        if "(" in receiver or "[" in receiver:
            return "complex"
        root = receiver.partition(".")[0]
        if root in self.declared_types or root in self.type_aliases:
            return "class_static"
        return "identifier"

    def _call(self, node: Any) -> None:
        name = self.text(node.child_by_field_name("name"))
        if not name:
            return
        object_node = node.child_by_field_name("object")
        metadata = {"syntax": "method_invocation"}
        target_module: str | None = None
        call_kind = "direct"
        if object_node is None:
            target = name
            if name in self.import_aliases:
                target, target_module = self._rewrite(name)
                metadata["static_import"] = True
        else:
            receiver = self.text(object_node).strip()
            if receiver == "this":
                target = name
                metadata["java_receiver"] = "this"
            elif receiver == "super":
                target = f"super.{name}"
                call_kind = "indirect"
                metadata["java_receiver"] = "super"
            elif "(" in receiver or "[" in receiver:
                target = f"{receiver}.{name}" if receiver else name
                call_kind = "indirect"
                metadata["callee_shape"] = "complex"
            else:
                target = f"{receiver}.{name}"
                if receiver.partition(".")[0] in self.import_aliases:
                    target, target_module = self._rewrite(target)
        metadata["receiver_shape"] = self._receiver_shape(object_node,
                                                           self.text(object_node).strip()
                                                           if object_node is not None else "")
        metadata["call_kind"] = call_kind
        self._ref(
            target, ref_type="CALLS", target_module=target_module, metadata=metadata,
            node=node.child_by_field_name("name"),
        )

    def _new(self, node: Any) -> None:
        type_node = node.child_by_field_name("type")
        if type_node is not None:
            base = self._base_text(type_node)
            if base:
                target, module = self._rewrite(base)
                self._ref(
                    target, ref_type="CALLS", target_module=module,
                    metadata={"syntax": "object_creation", "call_kind": "direct"}, node=type_node,
                )
        for child in node.named_children:
            if self._same_node(child, type_node) or child.type == "class_body":
                continue
            self._walk(child)

    def _explicit_ctor(self, node: Any) -> None:
        keyword = self.text(node.child_by_field_name("constructor")).strip()
        if keyword == "this":
            owner_type = self._innermost_type_name()
            if owner_type:
                self._ref(
                    owner_type, ref_type="CALLS",
                    metadata={"syntax": "explicit_constructor_invocation",
                              "java_constructor_invocation": "this", "call_kind": "direct"},
                    node=node,
                )
        elif keyword == "super":
            self._ref(
                "super", ref_type="CALLS",
                metadata={"syntax": "explicit_constructor_invocation",
                          "java_constructor_invocation": "super", "call_kind": "indirect"},
                node=node,
            )
        arguments = node.child_by_field_name("arguments")
        if arguments is not None:
            self._walk(arguments)

    def _method_ref(self, node: Any) -> None:
        named = node.named_children
        if len(named) < 2:
            return
        receiver = self.text(named[0]).strip()
        member = self.text(named[-1]).strip()
        if receiver and member and receiver != "::" and member != "::":
            self._ref(
                f"{receiver}.{member}", metadata={"syntax": "method_reference",
                                                  "call_kind": "indirect"},
                node=node,
            )

    def _field_access(self, node: Any) -> None:
        object_node = node.child_by_field_name("object")
        field_node = node.child_by_field_name("field")
        receiver = self.text(object_node).strip() if object_node is not None else ""
        if field_node is not None and receiver == "this":
            self._ref(
                self.text(field_node), metadata={"syntax": "field_access"}, node=field_node,
            )
        elif field_node is not None and receiver == "super":
            self._ref(
                f"super.{self.text(field_node)}",
                metadata={"syntax": "field_access", "call_kind": "indirect"}, node=field_node,
            )
        for child in node.named_children:
            if self._same_node(child, field_node):
                continue
            self._walk(child)

    def _annotation_usage(self, node: Any) -> None:
        name_node = node.child_by_field_name("name")
        name = self.text(name_node).strip()
        if name:
            if "." in name or name in self.import_aliases:
                target, module = self._rewrite(name)
                self._ref(
                    target, target_module=module, metadata={"syntax": "annotation"},
                    node=name_node,
                )
            elif name in self.declared_types:
                self._ref(name, metadata={"syntax": "annotation"}, node=name_node)
        for child in node.named_children:
            if self._same_node(child, name_node):
                continue
            self._walk(child)

    def _chained_type(self, node: Any) -> None:
        base = self._base_text(node)
        if not base:
            return
        target, module = self._rewrite(base)
        self._ref(target, target_module=module, metadata={"syntax": "type_usage"}, node=node)

    def _type_reference(self, node: Any) -> None:
        parent = node.parent
        if parent is None or parent.type in {
            "scoped_type_identifier", "generic_type", "type_parameters", "type_parameter",
        }:
            return
        target, module = self._rewrite(self.text(node))
        self._ref(target, target_module=module, metadata={"syntax": "type_usage"}, node=node)

    def _identifier_reference(self, node: Any) -> None:
        parent = node.parent
        if parent is None or parent.type in {
            "scoped_identifier", "method_reference", "labeled_statement",
            "break_statement", "continue_statement", "type_pattern",
            "inferred_parameters", "type_parameter",
        }:
            return
        name_node = parent.child_by_field_name("name")
        if name_node is not None and self._same_node(name_node, node):
            return
        target = self.text(node)
        if target in self.locals:
            return
        self._ref(target, metadata={"syntax": "identifier"}, node=node)

    # -- small helpers -----------------------------------------------------

    def _add_local(self, name_node: Any) -> None:
        if name_node is None:
            return
        name = self.text(name_node)
        if name:
            self.locals.add(name)

    def _add_lambda_params(self, parameters: Any) -> None:
        if parameters is None:
            return
        if parameters.type == "identifier":
            self._add_local(parameters)
            return
        for child in parameters.named_children:
            if child.type == "formal_parameter":
                self._add_local(child.child_by_field_name("name"))
            elif child.type == "inferred_parameters":
                for item in child.named_children:
                    self._add_local(item)

    def _innermost_type_name(self) -> str:
        for name, kind in reversed(self.scope):
            if kind in {"Class", "Interface"}:
                return name
        return ""
