from fastapi import FastAPI

from app.core.module_registry import register_module_group, register_service
from app.operations.adapters import register_operations_event_handlers
from app.operations.adapters.persistence import SqlAlchemyAuditLogRepository
from app.operations.adapters.api import router as operations_router
from app.operations.application import OperationsService


def register_operations_module(app: FastAPI) -> None:
    context = app.state.context
    repository = SqlAlchemyAuditLogRepository(context.database)
    service = OperationsService(repository=repository)
    register_service(app, "operations", service)
    register_module_group(app, "operations", ("operations",), routers=(operations_router,))
    register_operations_event_handlers(app)