# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastramqpi.context import Context
from pydantic import parse_obj_as

from mo_ldap_import_export.autogenerated_graphql_client.read_engagements_by_employee_uuid import (
    ReadEngagementsByEmployeeUuidEngagements,
)
from mo_ldap_import_export.customer_specific import CustomerSpecific
from mo_ldap_import_export.customer_specific import JobTitleFromADToMO
from mo_ldap_import_export.import_export import SyncTool


@pytest.fixture
def context(
    dataloader: AsyncMock,
    converter: MagicMock,
    export_checks: AsyncMock,
    settings: MagicMock,
) -> Context:
    context = Context(
        {
            "amqpsystem": AsyncMock(),
            "user_context": {
                "dataloader": dataloader,
                "converter": converter,
                "export_checks": export_checks,
                "settings": settings,
            },
        }
    )
    return context


async def test_template(sync_tool: SyncTool):
    temp = CustomerSpecific()
    await temp.sync_to_ldap()
    await temp.sync_to_mo(context=sync_tool.context)


async def test_import_jobtitlefromadtomo_objects(context: Context) -> None:
    test_eng_uuid = uuid4()
    start_time = datetime.now() - timedelta(minutes=10)
    end_time = datetime.now()

    graphql_client_mock = AsyncMock()
    graphql_client_mock.read_engagements_by_employee_uuid.return_value = parse_obj_as(
        ReadEngagementsByEmployeeUuidEngagements,
        {
            "objects": [
                {
                    "current": {
                        "uuid": str(test_eng_uuid),
                        "validity": {"from": str(start_time), "to": str(end_time)},
                    }
                }
            ]
        },
    )
    context["graphql_client"] = graphql_client_mock

    test_user_uuid = uuid4()
    test_job_function_uuid = uuid4()
    test_object = JobTitleFromADToMO.from_simplified_fields(
        user_uuid=test_user_uuid,
        job_function_uuid=test_job_function_uuid,
    )

    await test_object.sync_to_ldap()

    graphql_client_mock.set_job_title.assert_not_called()
    await test_object.sync_to_mo(context)

    graphql_client_mock.set_job_title.assert_called_once_with(
        job_function=test_job_function_uuid,
        uuid=test_eng_uuid,
        **{"from_": start_time, "to": end_time},
    )
    graphql_client_mock.set_job_title.assert_awaited_once_with(
        job_function=test_job_function_uuid,
        uuid=test_eng_uuid,
        **{"from_": start_time, "to": end_time},
    )
