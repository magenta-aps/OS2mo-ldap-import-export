# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
FROM python:3.10

ENV PYTHONUNBUFFERED 1

WORKDIR /app/

ENV POETRY_HOME=/opt/poetry \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/install-poetry.py | python --

COPY pyproject.toml poetry.lock* ./

RUN /opt/poetry/bin/poetry install --no-root --no-dev

COPY mo_ldap_import_export mo_ldap_import_export

CMD ["poetry", "run", "python", "-m",  "mo_ldap_import_export.ldap_agent"]
