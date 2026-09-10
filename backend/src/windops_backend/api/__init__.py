from fastapi import APIRouter

from windops_backend.api import (
    agents,
    alarms,
    assets,
    benchmarks,
    knowledge,
    missions,
    model_registry,
    operations,
    resources,
    scada,
    system,
    work_orders,
)

router = APIRouter()
for _module in (
    system,
    agents,
    assets,
    benchmarks,
    alarms,
    missions,
    work_orders,
    resources,
    scada,
    knowledge,
    model_registry,
    operations,
):
    # 扁平合并以保持与拆分前单一 APIRouter 完全一致的路由表（include_router 在新版
    # FastAPI 中会生成惰性 _IncludedRouter 包装，破坏对 router.routes 的直接内省）。
    router.routes.extend(_module.router.routes)

__all__ = ["router"]
