from fastapi import FastAPI

from app.core.module_registry import register_module_group, register_service
from app.interaction.adapters import register_interaction_event_handlers
from app.interaction.adapters.persistence import SqlAlchemyInteractionMessageRepository
from app.interaction.adapters.api import router as interaction_router
from app.interaction.application import InteractionService


def register_interaction_module(app: FastAPI) -> None:
    context = app.state.context
    repository = SqlAlchemyInteractionMessageRepository(context.database)
    service = InteractionService(context.event_bus, repository)
    register_service(app, "interaction", service)
    register_module_group(app, "interaction", ("interaction",), routers=(interaction_router,))
    register_interaction_event_handlers(app)