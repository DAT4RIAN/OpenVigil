from __future__ import annotations

import ast
import importlib
import tomllib
from collections.abc import Iterable
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[1] / "src"
PACKAGE_ROOT = SOURCE_ROOT / "windops_backend"
PYPROJECT_PATH = Path(__file__).parents[1] / "pyproject.toml"
PUBLIC_LIBRARY_ROOTS = frozenset({"windops_backend.benchmarks.care.online"})


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(SOURCE_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _internal_imports(path: Path, modules: frozenset[str]) -> Iterable[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    importer = _module_name(path)
    package = importer if path.name == "__init__.py" else importer.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in modules:
                    yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                prefix = package.split(".")
                base = prefix[: len(prefix) - node.level + 1]
                if node.module:
                    base.extend(node.module.split("."))
                target = ".".join(base)
            else:
                target = node.module or ""
            if target in modules:
                yield target
            for alias in node.names:
                candidate = f"{target}.{alias.name}" if target else alias.name
                if candidate in modules:
                    yield candidate


def _strongly_connected_components(graph: dict[str, frozenset[str]]) -> list[set[str]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[set[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for dependency in graph[node]:
            if dependency not in indices:
                visit(dependency)
                lowlinks[node] = min(lowlinks[node], lowlinks[dependency])
            elif dependency in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[dependency])
        if lowlinks[node] != indices[node]:
            return
        component: set[str] = set()
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.add(member)
            if member == node:
                break
        components.append(component)

    for node in graph:
        if node not in indices:
            visit(node)
    return components


def test_python_runtime_import_graph_has_no_multi_module_cycles() -> None:
    paths = tuple(PACKAGE_ROOT.rglob("*.py"))
    module_paths = {_module_name(path): path for path in paths}
    modules = frozenset(module_paths)
    graph = {
        module: frozenset(_internal_imports(path, modules)) - {module}
        for module, path in module_paths.items()
    }
    cycles = [
        sorted(component)
        for component in _strongly_connected_components(graph)
        if len(component) > 1
    ]
    assert cycles == []


def _console_scripts() -> dict[str, str]:
    document = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return dict(document["project"]["scripts"])


def test_all_console_script_targets_exist_and_are_callable() -> None:
    scripts = _console_scripts()
    assert len(scripts) == 27
    for name, target in scripts.items():
        module_name, separator, attribute_name = target.partition(":")
        assert separator == ":", name
        attribute = getattr(importlib.import_module(module_name), attribute_name)
        assert callable(attribute), name


def test_every_python_source_module_is_reachable_from_a_runtime_or_public_root() -> None:
    paths = tuple(PACKAGE_ROOT.rglob("*.py"))
    module_paths = {_module_name(path): path for path in paths}
    modules = frozenset(module_paths)
    graph = {
        module: frozenset(_internal_imports(path, modules)) - {module}
        for module, path in module_paths.items()
    }
    roots = {
        "windops_backend.main",
        *PUBLIC_LIBRARY_ROOTS,
        *(target.partition(":")[0] for target in _console_scripts().values()),
    }
    reachable: set[str] = set()
    pending = list(roots)
    while pending:
        module = pending.pop()
        if module in reachable:
            continue
        reachable.add(module)
        pending.extend(graph.get(module, ()))

    package_namespaces = {
        module for module, path in module_paths.items() if path.name == "__init__.py"
    }
    assert sorted(modules - reachable - package_namespaces) == []
