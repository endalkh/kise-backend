"""Every mapper implementation must satisfy the contract its domain declares.

The contracts in ``<context>/domain/mappers.py`` are ports: the domain says what translation must be
possible, infrastructure says how. Without this test the ports would be documentation. With it, an
implementation that renames ``to_model`` or forgets ``update_model`` fails the build.
"""

from __future__ import annotations

import pytest

from kise.expense_tracking.domain.mappers import (
    CategoryMapping,
    ExpenseMapping,
    FixedExpenseMapping,
)
from kise.expense_tracking.infrastructure.persistence.mappers import (
    CategoryMapper,
    ExpenseMapper,
    FixedExpenseMapper,
    SettlementMapper,
)
from kise.identity.domain.mappers import OwnerMapping
from kise.identity.infrastructure.persistence.mappers import OwnerMapper
from kise.shared_kernel.domain.mapper import Mapper

IMPLEMENTATIONS = [
    (OwnerMapper, OwnerMapping),
    (CategoryMapper, CategoryMapping),
    (ExpenseMapper, ExpenseMapping),
    (FixedExpenseMapper, FixedExpenseMapping),
]


@pytest.mark.parametrize(
    ("implementation", "contract"),
    IMPLEMENTATIONS,
    ids=lambda item: getattr(item, "__name__", str(item)),
)
def test_implementation_satisfies_its_domain_contract(implementation, contract):
    assert issubclass(implementation, contract), (
        f"{implementation.__name__} does not satisfy {contract.__name__}"
    )


@pytest.mark.parametrize(
    "implementation", [impl for impl, _ in IMPLEMENTATIONS], ids=lambda i: i.__name__
)
def test_implementation_satisfies_the_generic_mapper_protocol(implementation):
    assert issubclass(implementation, Mapper)


@pytest.mark.parametrize(
    "implementation", [impl for impl, _ in IMPLEMENTATIONS], ids=lambda i: i.__name__
)
def test_the_three_operations_are_all_present(implementation):
    for operation in ("to_model", "to_domain", "update_model"):
        assert callable(getattr(implementation, operation, None)), (
            f"{implementation.__name__}.{operation} is missing"
        )


def test_settlement_has_no_contract_because_it_is_a_child_entity():
    """A Settlement is only ever persisted as part of its FixedExpense, so no port exists for it —
    and its mapper deliberately takes the owner id from the root rather than standing alone."""
    import kise.expense_tracking.domain.mappers as contracts

    assert not hasattr(contracts, "SettlementMapping")
    # to_model requires the root's owner id, so it cannot be called as a standalone mapper.
    with pytest.raises(TypeError):
        SettlementMapper.to_model(object())  # type: ignore[call-arg]
