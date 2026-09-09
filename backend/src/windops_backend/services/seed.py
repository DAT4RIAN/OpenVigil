from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.agents.tools import TOOL_CATALOG, TOOL_CATALOG_VERSION
from windops_backend.models import (
    AgentDefinition,
    AgentSkillLink,
    AgentToolLink,
    AssetHealthEvent,
    CatalogVersion,
    KnowledgeDocument,
    Resource,
    SkillDefinition,
    ToolDefinition,
    Turbine,
    WeatherWindow,
    WindFarm,
)

CATALOG_VERSION_ID = "wt023-catalog-2026.08"
CATALOG_VERSION = TOOL_CATALOG_VERSION

AGENT_CATALOG: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "scada_analysis_agent",
        "SCADA Analysis Agent",
        "scada-analysis",
        ("get_turbine_status", "query_scada", "query_alarm_history"),
    ),
    (
        "vibration_diagnosis_agent",
        "Vibration Diagnosis Agent",
        "vibration-diagnosis",
        ("query_scada", "query_vibration", "calculate_health_score", "predict_rul"),
    ),
    (
        "knowledge_agent",
        "Knowledge Agent",
        "knowledge-retrieval",
        ("query_similar_failures", "query_maintenance_history"),
    ),
    (
        "failure_diagnosis_agent",
        "Failure Diagnosis Agent",
        "failure-diagnosis",
        ("query_alarm_history", "query_vibration", "query_similar_failures"),
    ),
    (
        "maintenance_strategy_agent",
        "Maintenance Strategy Agent",
        "maintenance-strategy",
        (
            "query_weather",
            "query_maintenance_history",
            "calculate_health_score",
            "predict_rul",
            "create_decision",
        ),
    ),
    (
        "review_committee",
        "Review Committee",
        "multidisciplinary-review",
        ("get_turbine_status", "query_weather", "query_similar_failures"),
    ),
    ("human_approval_gate", "Human Approval Gate", "human-approval", ()),
    (
        "work_order_agent",
        "Work Order Agent",
        "work-order-orchestration",
        ("get_turbine_status", "query_weather", "create_work_order"),
    ),
)


async def seed_agent_catalog(session: AsyncSession) -> None:
    if await session.get(CatalogVersion, CATALOG_VERSION_ID) is None:
        session.add(
            CatalogVersion(
                id=CATALOG_VERSION_ID,
                version=CATALOG_VERSION,
                description="Versioned WT-023 LangGraph agent, skill, and tool catalog",
                active=True,
            )
        )

    for item in TOOL_CATALOG:
        tool_id = f"tool:{item['name']}@{CATALOG_VERSION}"
        if await session.get(ToolDefinition, tool_id) is None:
            session.add(
                ToolDefinition(
                    id=tool_id,
                    tool_key=item["name"],
                    mode=item["mode"],
                    version=CATALOG_VERSION,
                    catalog_version_id=CATALOG_VERSION_ID,
                    description=f"WT-023 domain tool {item['name']}",
                )
            )

    for agent_key, display_name, skill_key, _ in AGENT_CATALOG:
        agent_id = f"agent:{agent_key}@{CATALOG_VERSION}"
        skill_id = f"skill:{skill_key}@{CATALOG_VERSION}"
        if await session.get(AgentDefinition, agent_id) is None:
            session.add(
                AgentDefinition(
                    id=agent_id,
                    agent_key=agent_key,
                    display_name=display_name,
                    role=agent_key,
                    version=CATALOG_VERSION,
                    catalog_version_id=CATALOG_VERSION_ID,
                    description=f"Auditable WT-023 graph role: {display_name}",
                    active=True,
                )
            )
        if await session.get(SkillDefinition, skill_id) is None:
            session.add(
                SkillDefinition(
                    id=skill_id,
                    skill_key=skill_key,
                    display_name=skill_key.replace("-", " ").title(),
                    version=CATALOG_VERSION,
                    catalog_version_id=CATALOG_VERSION_ID,
                    description=f"Versioned capability for {display_name}",
                )
            )

    await session.flush()
    tool_ids = {item["name"]: f"tool:{item['name']}@{CATALOG_VERSION}" for item in TOOL_CATALOG}
    for agent_key, _, skill_key, tool_keys in AGENT_CATALOG:
        agent_id = f"agent:{agent_key}@{CATALOG_VERSION}"
        skill_id = f"skill:{skill_key}@{CATALOG_VERSION}"
        if await session.get(AgentSkillLink, (agent_id, skill_id)) is None:
            session.add(
                AgentSkillLink(
                    agent_definition_id=agent_id,
                    skill_definition_id=skill_id,
                    catalog_version_id=CATALOG_VERSION_ID,
                )
            )
        for tool_key in tool_keys:
            tool_id = tool_ids[tool_key]
            if await session.get(AgentToolLink, (agent_id, tool_id)) is None:
                session.add(
                    AgentToolLink(
                        agent_definition_id=agent_id,
                        tool_definition_id=tool_id,
                        catalog_version_id=CATALOG_VERSION_ID,
                    )
                )


async def seed_wt023_demo(session: AsyncSession) -> None:
    """Seed only reference/master data; the anomaly and workflow are never pre-created."""

    await seed_agent_catalog(session)

    if await session.scalar(select(WindFarm.id).where(WindFarm.id == "WF-EAST-01")) is None:
        session.add(
            WindFarm(id="WF-EAST-01", name="East China Offshore Wind Farm", capacity_mw=384)
        )

    if await session.get(Turbine, "WT-023") is None:
        session.add(
            Turbine(
                id="WT-023",
                wind_farm_id="WF-EAST-01",
                model="Goldwind GW165-6.0MW",
                status="running",
                health_score=96,
            )
        )
        session.add(
            AssetHealthEvent(
                id="HEALTH-WT023-BASELINE",
                turbine_id="WT-023",
                score=96,
                status="healthy",
                reason="commissioned normal-state baseline",
            )
        )

    manual = await session.get(KnowledgeDocument, "KB-MB-GW165-001")
    if manual is None:
        session.add(
            KnowledgeDocument(
                id="KB-MB-GW165-001",
                title="GW165 Main Bearing Inspection Procedure",
                document_type="manufacturer_manual",
                body=(
                    "Inspect lubrication, acquire vibration spectrum and bearing temperature, "
                    "perform borescope inspection, and retain field photographs. Rising RMS with "
                    "temperature supports an early degradation diagnosis."
                ),
                # The reference pack stores controlled text in PostgreSQL. It
                # deliberately does not claim that a MinIO object was uploaded.
                citation_uri="windops://knowledge/documents/KB-MB-GW165-001",
                vectorized=False,
            )
        )

    resources = (
        ("CREW-MECH-A", "crew", "Mechanical Maintenance Team A", 1),
        ("VESSEL-HAIDONG-7", "vessel", "Haidong 7", 1),
        ("SPARE-MB-GW165", "spare_part", "GW165 Main Bearing Kit", 2),
    )
    for resource_id, resource_type, name, quantity in resources:
        if await session.get(Resource, resource_id) is None:
            session.add(
                Resource(
                    id=resource_id,
                    resource_type=resource_type,
                    name=name,
                    quantity=quantity,
                )
            )

    if await session.scalar(select(WeatherWindow.id).limit(1)) is None:
        start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=24)
        session.add(
            WeatherWindow(
                id="WEATHER-WINDOW-WT023",
                wind_farm_id="WF-EAST-01",
                starts_at=start,
                ends_at=start + timedelta(hours=8),
                wind_speed_ms=8.1,
                wave_height_m=1.4,
                suitable=True,
            )
        )
    await session.commit()
