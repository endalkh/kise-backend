"""Application services of the Identity context — one per aggregate.

These are what the presentation layer calls. Routers depend on a service and nothing else.
"""

from kise.identity.application.services.owners import OwnerService

__all__ = ["OwnerService"]
