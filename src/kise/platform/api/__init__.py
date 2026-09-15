"""The HTTP presentation layer's composition: app factory, dependencies, error mapping.

This lives in ``platform/`` rather than in a context because assembling routers from three contexts
into one FastAPI app is wiring — the same reason the Unit of Work and the container live here. The
per-context routers themselves live in each context's ``presentation/`` package.
"""
