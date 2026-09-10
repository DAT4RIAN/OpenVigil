from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter
from fastapi.routing import APIRoute

from windops_backend.api import router as business_router
from windops_backend.knowledge_graph.api import router as knowledge_graph_router

EXPECTED_API_ROUTE_COUNT = 95
EXPECTED_API_ROUTE_SHA256 = "653247fa7cada71548edeccba02bd0c04f68f03fad14261613338db3ee68790d"


def _route_signature(router: APIRouter) -> list[dict[str, Any]]:
    return [
        {
            "path": f"/api/v1{route.path}",
            "methods": sorted(route.methods or ()),
            "name": route.name,
        }
        for route in router.routes
        if isinstance(route, APIRoute)
    ]


def test_fastapi_public_route_surface_matches_the_recorded_baseline() -> None:
    routes = [
        *_route_signature(business_router),
        *_route_signature(knowledge_graph_router),
    ]
    canonical = json.dumps(
        sorted(routes, key=lambda row: (row["path"], row["methods"], row["name"])),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert len(routes) == EXPECTED_API_ROUTE_COUNT
    assert hashlib.sha256(canonical).hexdigest() == EXPECTED_API_ROUTE_SHA256
