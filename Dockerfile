FROM python:3.10

# Main program
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1
RUN pip install --no-cache-dir poetry==1.4.2

WORKDIR /opt
COPY poetry.lock pyproject.toml ./
RUN poetry install --no-dev

COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY docker ./docker
COPY db ./db
COPY mo_ldap_import_export ./mo_ldap_import_export

# Default command
CMD ["./docker/start.sh"]

# Add build version to the environment last to avoid build cache misses
ARG COMMIT_TAG
ARG COMMIT_SHA
ENV COMMIT_TAG=${COMMIT_TAG:-HEAD} \
    COMMIT_SHA=${COMMIT_SHA}
