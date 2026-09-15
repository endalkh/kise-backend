"""Entities of the Identity context — identity by id, mutable, rule-carrying.

``Owner`` is the only aggregate root here. Value objects live next door in ``value_objects.py``.
"""

from kise.identity.domain.entities.owner import Owner

__all__ = ["Owner"]
