"""The dependency rule, enforced instead of merely documented (NFR-9).

    presentation -> application -> domain
    infrastructure -> domain

The domain layer is pure: it may import the standard library and other *domain* modules, and
nothing else. If someone reaches for SQLAlchemy or FastAPI inside an aggregate, this test fails
before a reviewer has to notice.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
KISE = SRC / "kise"

CONTEXTS = ("identity", "expense_tracking", "reporting")
FORBIDDEN_IN_DOMAIN_PREFIXES = (
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "starlette",
    "jwt",
    "bcrypt",
    "httpx",
    "uvicorn",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import, stays inside the same package
                continue
            if node.module:
                modules.add(node.module)
    return modules


def _python_files(*parts: str) -> list[Path]:
    root = KISE.joinpath(*parts)
    return sorted(p for p in root.rglob("*.py") if root.exists())


def test_src_layout_exists():
    assert KISE.is_dir(), f"expected the DDD source tree at {KISE}"
    assert (KISE / "shared_kernel" / "domain").is_dir()


DOMAIN_FILES = [
    p
    for parts in (("shared_kernel", "domain"), *[(c, "domain") for c in CONTEXTS])
    for p in _python_files(*parts)
]


@pytest.mark.parametrize("path", DOMAIN_FILES, ids=lambda p: str(p.relative_to(KISE)))
def test_domain_imports_nothing_outward(path: Path):
    for module in _imported_modules(path):
        root = module.split(".")[0]
        assert root not in FORBIDDEN_IN_DOMAIN_PREFIXES, (
            f"{path.relative_to(KISE)} imports {module}; the domain layer must stay pure"
        )
        if root == "kise":
            parts = module.split(".")
            assert "application" not in parts, f"{path.name} imports application code: {module}"
            assert "infrastructure" not in parts, (
                f"{path.name} imports infrastructure code: {module}"
            )
            assert "presentation" not in parts, f"{path.name} imports presentation code: {module}"
            assert "platform" not in parts, f"{path.name} imports the composition root: {module}"
            # A database models module is infrastructure, already caught above. Spelled out
            # because it is the mistake most worth naming: use a mapper, not a table.
            assert not module.endswith("persistence.models"), (
                f"{path.name} imports database models; use a mapper instead"
            )


MODEL_FILES = [
    path
    for context in CONTEXTS
    for path in [KISE / context / "infrastructure" / "persistence" / "models.py"]
    if path.is_file()
]


def test_no_module_is_shadowed_by_a_package_of_the_same_name():
    """``foo.py`` next to ``foo/`` is a silent trap: Python imports the package and the module
    becomes unreachable, with no error at import time and no error from the linter.

    This actually happened during development — ``identity/application/use_cases.py`` sat beside an
    empty ``use_cases/``, and every class in it was invisible.
    """
    clashes = []
    for directory in [KISE, *(p for p in KISE.rglob("*") if p.is_dir())]:
        if "__pycache__" in directory.parts:
            continue
        for package in (p for p in directory.iterdir() if p.is_dir()):
            if (directory / f"{package.name}.py").is_file():
                clashes.append(str((directory / package.name).relative_to(KISE)))
    assert clashes == [], f"module shadowed by a package of the same name: {clashes}"


def test_repositories_exist_only_in_infrastructure():
    """One repository class per aggregate, in one place: infrastructure.

    There is no abstract port mirroring each concrete repository. That was a deliberate
    simplification — a second hierarchy that only ever has one implementation is a file to keep in
    sync, not a seam anyone uses. Tests substitute fakes by duck typing instead.
    """
    for context in ("identity", "expense_tracking"):
        for layer in ("domain", "application"):
            base = KISE / context / layer
            for name in ("repository.py", "repositories.py", "repository", "repositories"):
                assert not (base / name).exists(), (
                    f"{context}/{layer}/{name} exists; repositories belong in infrastructure"
                )

    assert (
        KISE / "identity" / "infrastructure" / "persistence" / "repository.py"
    ).is_file()
    assert (
        KISE / "expense_tracking" / "infrastructure" / "persistence" / "repositories.py"
    ).is_file()


def test_each_context_separates_entities_value_objects_and_mapping_contracts():
    """The domain layout is a convention worth enforcing, so a new context copies it correctly.

    ``entities/``        identity by id, mutable
    ``value_objects``    compared by value, immutable
    ``models``           the facade both are imported through
    ``mappers.py``       mapping contracts (ports); implementations live in infrastructure
    """
    for context in ("identity", "expense_tracking"):
        domain = KISE / context / "domain"
        assert (domain / "entities").is_dir(), f"{context} has no domain/entities"
        assert (domain / "models" / "__init__.py").is_file(), f"{context} has no domain/models"
        mappers = domain / "mappers"
        assert mappers.is_dir() or mappers.with_suffix(".py").is_file(), (
            f"{context} has no domain/mappers"
        )
        value_objects = domain / "value_objects"
        assert value_objects.is_dir() or value_objects.with_suffix(".py").is_file(), (
            f"{context} has no domain/value_objects"
        )


@pytest.mark.parametrize("context", ["identity", "expense_tracking"])
def test_mapping_contracts_stay_free_of_infrastructure(context: str):
    """``domain/mappers.py`` declares *what* must be translatable, never how. If it imported a
    models module or SQLAlchemy, the dependency rule would be inverted."""
    root = KISE / context / "domain" / "mappers"
    contracts = sorted(root.rglob("*.py")) if root.is_dir() else [root.with_suffix(".py")]
    for module in {m for path in contracts for m in _imported_modules(path)}:
        root = module.split(".")[0]
        assert module.split(".")[0] not in FORBIDDEN_IN_DOMAIN_PREFIXES, (
            f"{context}/domain/mappers imports {module}"
        )
        assert not module.endswith("persistence.models"), (
            f"{context}/domain/mappers imports database models: {module}"
        )


def test_each_context_owns_its_own_models_module():
    """Tables belong to the context whose aggregates they store, not to a shared dumping ground."""
    assert (KISE / "identity" / "infrastructure" / "persistence" / "models.py").is_file()
    assert (KISE / "expense_tracking" / "infrastructure" / "persistence" / "models.py").is_file()
    assert not (KISE / "platform" / "models.py").exists(), (
        "database models were consolidated again; they belong per context"
    )


@pytest.mark.parametrize("path", MODEL_FILES, ids=lambda p: str(p.relative_to(KISE)))
def test_database_models_hold_no_rules(path: Path):
    """A models module is the schema. It must not import the domain, which would invert the
    dependency and let a table dictate a rule — nor another context's models."""
    own_context = path.relative_to(KISE).parts[0]
    for module in _imported_modules(path):
        parts = module.split(".")
        if parts[0] != "kise":
            continue
        assert "domain" not in parts, f"{path.relative_to(KISE)} imports domain code: {module}"
        if len(parts) > 1 and parts[1] in CONTEXTS:
            assert parts[1] == own_context, (
                f"{path.relative_to(KISE)} imports {module}: a context's tables must not import "
                "another context's. Reference by table name if a foreign key is really wanted."
            )


APPLICATION_FILES = [p for c in CONTEXTS for p in _python_files(c, "application")]

#: Use cases talk to repositories directly, by deliberate choice: fewer files, no parallel
#: hierarchy of abstract ports mirroring the concrete classes. The cost is that a use case's
#: import list now names its persistence, so swapping it means editing use cases.
#:
#: The line is drawn at repositories. Everything else in infrastructure — mappers, database models,
#: the bcrypt and JWT adapters — stays behind a port, so a rule still cannot reach a table or a
#: hashing algorithm.
ALLOWED_INFRASTRUCTURE_IMPORTS_FROM_APPLICATION = (
    "persistence.repositories",
    "persistence.repository",
)


@pytest.mark.parametrize(
    "path", APPLICATION_FILES, ids=lambda p: str(p.relative_to(KISE)) if APPLICATION_FILES else ""
)
def test_application_imports_only_repositories_from_infrastructure(path: Path):
    for module in _imported_modules(path):
        parts = module.split(".")
        if parts[0] != "kise":
            continue
        assert "presentation" not in parts, (
            f"{path.relative_to(KISE)} imports {module}; the application layer must not know HTTP"
        )
        if "infrastructure" in parts:
            assert module.endswith(ALLOWED_INFRASTRUCTURE_IMPORTS_FROM_APPLICATION), (
                f"{path.relative_to(KISE)} imports {module}. Only repositories may be imported "
                "from infrastructure; mappers, database models and security adapters stay behind "
                "a port."
            )


@pytest.mark.parametrize(
    "path", APPLICATION_FILES, ids=lambda p: str(p.relative_to(KISE)) if APPLICATION_FILES else ""
)
def test_application_never_touches_database_models_or_sqlalchemy(path: Path):
    """The looser repository rule must not become a licence to write SQL in a use case."""
    for module in _imported_modules(path):
        root = module.split(".")[0]
        assert root != "sqlalchemy", f"{path.relative_to(KISE)} imports SQLAlchemy directly"
        assert not module.endswith("persistence.models"), (
            f"{path.relative_to(KISE)} imports database models: {module}"
        )


ALL_CONTEXT_FILES = [p for c in CONTEXTS for p in _python_files(c)]


@pytest.mark.parametrize(
    "path", ALL_CONTEXT_FILES, ids=lambda p: str(p.relative_to(KISE)) if ALL_CONTEXT_FILES else ""
)
def test_bounded_contexts_do_not_import_each_other(path: Path):
    """Contexts integrate through domain events, not by importing each other's models."""
    own_context = path.relative_to(KISE).parts[0]
    for module in _imported_modules(path):
        parts = module.split(".")
        if parts[0] != "kise" or len(parts) < 2:
            continue
        target = parts[1]
        if target in CONTEXTS and target != own_context:
            pytest.fail(
                f"{path.relative_to(KISE)} imports {module}: cross-context import from "
                f"{own_context} into {target}. Integrate through a domain event."
            )


def test_shared_kernel_depends_on_no_context():
    for path in _python_files("shared_kernel"):
        for module in _imported_modules(path):
            parts = module.split(".")
            if parts[0] == "kise" and len(parts) > 1:
                assert parts[1] not in CONTEXTS, (
                    f"shared kernel file {path.name} imports context code: {module}"
                )
