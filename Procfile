# Heroku process definitions.
#
# release: runs once per deploy, before the new web dynos start. Alembic owns the schema, so
#          migrations run here instead of at boot. alembic.ini already sets prepend_sys_path=src.
# web:     Heroku injects $PORT and kills a dyno that binds anything else.
#          PYTHONPATH=src is required because requirements.txt installs the dependencies only,
#          not this package (src layout); it is harmless when the package is installed.
release: alembic upgrade head
web: PYTHONPATH=src uvicorn kise.platform.api.app:app --host 0.0.0.0 --port $PORT
