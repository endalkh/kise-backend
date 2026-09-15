"""Domain models of the Identity context — one import point for entities and value objects.

"Model" here means a *domain* model, something that carries rules. The split behind this facade:

``entities/``          identity by id, mutable: ``Owner``
``value_objects.py``   compared by value, immutable: ``EmailAddress``, ``PasswordHash``,
                       ``Preferences``

Not to be confused with this context's ``infrastructure/persistence/models.py``, which holds the
database tables. These classes know nothing about SQLAlchemy; mappers translate between the two.
"""

from kise.identity.domain.entities import Owner
from kise.identity.domain.value_objects import (
    MAX_DISPLAY_NAME_LENGTH,
    MAX_EMAIL_LENGTH,
    EmailAddress,
    PasswordHash,
    Preferences,
    clean_display_name,
)

__all__ = [
    "MAX_DISPLAY_NAME_LENGTH",
    "MAX_EMAIL_LENGTH",
    "EmailAddress",
    "Owner",
    "PasswordHash",
    "Preferences",
    "clean_display_name",
]
