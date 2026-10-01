import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import aliased

import windops_backend.access_control as access_control
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import Turbine, WindFarm


@pytest.mark.asyncio
async def test_repeated_scoped_reads_share_criteria_and_preserve_alias_visibility(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = access_control._loader_criteria
    builds = []

    def counted(policy: GraphAccessPolicy):
        builds.append(policy)
        return original(policy)

    monkeypatch.setattr(access_control, "_loader_criteria", counted)
    policy = GraphAccessPolicy.from_values(turbine_ids=["WT-023"], data_scopes=["asset"])
    async with app.state.session_factory() as session:
        access_control.attach_access_policy(session, policy)
        assert list(await session.scalars(select(Turbine.id))) == ["WT-023"]
        turbine_alias = aliased(Turbine)
        assert list(await session.scalars(select(turbine_alias.id))) == ["WT-023"]
        assert list(await session.scalars(select(WindFarm.id))) == []
        assert list(await session.scalars(select(Turbine.id))) == ["WT-023"]
    assert builds == [policy]


@pytest.mark.asyncio
@pytest.mark.parametrize("direct_rebind", [False, True])
@pytest.mark.parametrize(
    "restricted_policy",
    [
        GraphAccessPolicy.from_values(turbine_ids=["WT-NOT-OWNED"], data_scopes=["asset"]),
        GraphAccessPolicy.from_values(
            turbine_ids=["WT-023"], entity_ids=["WT-NOT-OWNED"], data_scopes=["asset"]
        ),
    ],
)
async def test_session_rebind_never_reuses_previous_asset_or_entity_grant(
    app: FastAPI, restricted_policy: GraphAccessPolicy, direct_rebind: bool
) -> None:
    initial = GraphAccessPolicy.from_values(turbine_ids=["WT-023"], data_scopes=["asset"])
    async with app.state.session_factory() as session:
        access_control.attach_access_policy(session, initial)
        assert list(await session.scalars(select(Turbine.id))) == ["WT-023"]
        if direct_rebind:
            session.sync_session.info[access_control.ACCESS_POLICY_SESSION_KEY] = restricted_policy
        else:
            access_control.attach_access_policy(session, restricted_policy)
        assert list(await session.scalars(select(Turbine.id))) == []
        assert list(await session.scalars(select(aliased(Turbine).id))) == []
        access_control.attach_access_policy(session, initial)
        assert list(await session.scalars(select(Turbine.id))) == ["WT-023"]


@pytest.mark.asyncio
async def test_criteria_reuse_is_private_to_each_session(app: FastAPI) -> None:
    allowed = GraphAccessPolicy.from_values(turbine_ids=["WT-023"], data_scopes=["asset"])
    denied = GraphAccessPolicy.from_values(turbine_ids=["WT-NOT-OWNED"], data_scopes=["asset"])
    async with app.state.session_factory() as first, app.state.session_factory() as second:
        access_control.attach_access_policy(first, allowed)
        access_control.attach_access_policy(second, denied)
        assert list(await first.scalars(select(Turbine.id))) == ["WT-023"]
        assert list(await second.scalars(select(Turbine.id))) == []
        assert list(await first.scalars(select(aliased(Turbine).id))) == ["WT-023"]
        assert list(await second.scalars(select(aliased(Turbine).id))) == []


@pytest.mark.asyncio
async def test_endpoint_data_domain_remains_independent_of_row_criteria_reuse(
    client: AsyncClient,
) -> None:
    headers = {
        "X-WindOps-Test-Principal": "criteria-domain-manager",
        "X-WindOps-Test-Role": "operations_manager",
        "X-WindOps-Test-Turbine-Ids": "WT-023",
        "X-WindOps-Test-Data-Scopes": "asset",
    }
    allowed = await client.get("/api/v1/turbines", headers=headers)
    assert allowed.status_code == 200, allowed.text
    assert [row["turbine_id"] for row in allowed.json()["turbines"]] == ["WT-023"]
    denied = await client.get(
        "/api/v1/turbines", headers={**headers, "X-WindOps-Test-Data-Scopes": "mission"}
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "DATA_SCOPE_FORBIDDEN"
