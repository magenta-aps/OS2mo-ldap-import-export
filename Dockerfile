# SPDX-FileCopyrightText: 2022 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
FROM python:3.10

ENV PYTHONUNBUFFERED 1

WORKDIR /app/

ENV POETRY_HOME=/usr/local/bin/poetry \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir poetry==1.1.13

COPY pyproject.toml poetry.lock* ./

RUN poetry install --no-root --no-dev

COPY mo_ldap_import_export mo_ldap_import_export

CMD ["poetry", "run", "python", "-m",  "mo_ldap_import_export.ldap_agent"]
