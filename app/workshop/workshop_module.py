from fastapi import FastAPI

from app.core.module_registry import register_module_group, register_service
from app.workshop.adapters.persistence import SqlAlchemyWorkshopRepository
from app.workshop.application.service import WorkshopService


def register_workshop_module(app: FastAPI) -> None:
    context = app.state.context
    repository = SqlAlchemyWorkshopRepository(context.database)
    service = WorkshopService(repository=repository, event_bus=context.event_bus)
    register_service(app, "workshop", service)

    from app.workshop.adapters.api.routes import router as workshop_router
    from app.workshop.adapters.events import register_workshop_event_handlers

    register_module_group(app, "workshop", ("workshop",), routers=(workshop_router,))
    register_workshop_event_handlers(app)
