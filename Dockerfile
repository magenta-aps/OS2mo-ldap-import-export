FROM python:3.10


ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1
RUN pip install --no-cache-dir poetry==1.1.13

WORKDIR /opt
COPY poetry.lock pyproject.toml ./
RUN poetry install --no-root --no-dev

WORKDIR /opt/app
COPY mo_ldap_import_export .
WORKDIR /opt/




# ENV POETRY_HOME=/usr/local/bin/poetry



CMD ["poetry", "run", "python", "-m",  "mo_ldap_import_export.ldap_agent"]
