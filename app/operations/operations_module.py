from fastapi import FastAPI

from app.core.module_registry import register_module_group, register_service
from app.operations.adapters.persistence import SqlAlchemyAuditLogRepository
from app.operations.adapters.persistence import SqlAlchemySagaWorkflowRepository
from app.operations.application.service import OperationsService


def register_operations_module(app: FastAPI) -> None:
    context = app.state.context
    repository = SqlAlchemyAuditLogRepository(context.database)
    saga_repository = SqlAlchemySagaWorkflowRepository(context.database)
    service = OperationsService(
        repository=repository,
        event_bus=context.event_bus,
        saga_repository=saga_repository,
    )
    register_service(app, "operations", service)
    from app.operations.adapters.api.routes import router as operations_router
    from app.operations.adapters.events import register_operations_event_handlers

    register_module_group(app, "operations", ("operations",), routers=(operations_router,))
    register_operations_event_handlers(app)