from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from kise.shared_kernel.domain.entity import AggregateRoot, Entity
from kise.shared_kernel.domain.errors import ValidationError
from kise.shared_kernel.domain.events import DomainEvent
from kise.shared_kernel.domain.identifiers import CategoryId, ExpenseId, OwnerId


def test_ids_are_generated_in_the_domain():
    an_id = ExpenseId.new()
    assert isinstance(an_id.value, UUID)
    assert ExpenseId.parse(str(an_id)) == an_id


def test_id_types_do_not_mix():
    raw = uuid4()
    assert OwnerId(raw) != CategoryId(raw)
    assert OwnerId(raw) == OwnerId(raw)


def test_invalid_ids_are_rejected():
    with pytest.raises(ValidationError):
        ExpenseId.parse("not-a-uuid")
    with pytest.raises(ValidationError):
        ExpenseId("not-a-uuid")  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True, kw_only=True)
class ThingHappened(DomainEvent):
    thing: str


class Thing(AggregateRoot):
    def __init__(self, entity_id: ExpenseId, label: str) -> None:
        super().__init__(entity_id)
        self.label = label

    def relabel(self, label: str) -> None:
        self.label = label
        self.record_event(ThingHappened(thing=label))


def test_entities_are_equal_by_id_not_by_state():
    an_id = ExpenseId.new()
    assert Thing(an_id, "a") == Thing(an_id, "b")
    assert Thing(an_id, "a") != Thing(ExpenseId.new(), "a")
    assert len({Thing(an_id, "a"), Thing(an_id, "b")}) == 1


def test_entities_of_different_types_are_never_equal():
    an_id = ExpenseId.new()

    class Other(Entity):
        pass

    assert Thing(an_id, "a") != Other(an_id)


def test_events_are_recorded_then_drained_once():
    thing = Thing(ExpenseId.new(), "a")
    assert not thing.has_pending_events
    thing.relabel("b")
    thing.relabel("c")
    assert thing.has_pending_events

    events = thing.pull_events()
    assert [e.thing for e in events] == ["b", "c"]
    assert [e.name for e in events] == ["ThingHappened", "ThingHappened"]
    assert thing.pull_events() == []
    assert not thing.has_pending_events


def test_events_carry_identity_and_a_timestamp():
    first = ThingHappened(thing="x")
    second = ThingHappened(thing="x")
    assert first.event_id != second.event_id
    assert first.occurred_at.tzinfo is not None
