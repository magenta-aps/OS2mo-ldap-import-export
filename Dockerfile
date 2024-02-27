FROM python:3.10

# Main program
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1
RUN pip install --no-cache-dir poetry==1.4.2

WORKDIR /opt
COPY poetry.lock pyproject.toml ./
ARG POETRY_INSTALL_ARGS="--only-root"
RUN poetry install ${POETRY_INSTALL_ARGS}

WORKDIR /opt/app
COPY mo_ldap_import_export .
WORKDIR /opt/

# Default command
CMD [ "uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0" ]

ENV POETRY_INSTALL_ARGS=${POETRY_INSTALL_ARGS}

# Add build version to the environment last to avoid build cache misses
ARG COMMIT_TAG
ARG COMMIT_SHA
ENV COMMIT_TAG=${COMMIT_TAG:-HEAD} \
    COMMIT_SHA=${COMMIT_SHA}
