"""The mapping contract — a port, declared in the domain, implemented in infrastructure.

The domain does not translate anything itself. What it does own is the *specification* of the
translation, for the same reason it owns ``OwnerRepository``: "how an aggregate is turned into
storage and back" is part of the model's vocabulary, while the SQLAlchemy that does it is not.

Three operations, and the third matters as much as the first two:

``to_model``      a new aggregate becomes a new row
``to_domain``     a row is rehydrated into an aggregate
``update_model``  an already-loaded row is brought in line with a mutated aggregate

Implementations live in ``<context>/infrastructure/persistence/mappers.py``, and a contract test
asserts each one satisfies the protocol declared here. ``ModelT`` is deliberately unconstrained: the
domain must not know what a row looks like.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

AggregateT = TypeVar("AggregateT")
ModelT = TypeVar("ModelT")


@runtime_checkable
class Mapper(Protocol[AggregateT, ModelT]):
    """Translates one aggregate between its domain form and its stored form."""

    @staticmethod
    def to_model(aggregate: AggregateT) -> Any: ...

    @staticmethod
    def to_domain(model: Any) -> AggregateT: ...

    @staticmethod
    def update_model(model: Any, aggregate: AggregateT) -> None: ...
