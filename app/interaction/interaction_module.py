from fastapi import FastAPI

from app.core.module_registry import register_module_group, register_service
from app.interaction.adapters import register_interaction_event_handlers
from app.interaction.adapters.api import router as interaction_router
from app.interaction.adapters.realtime import router as interaction_realtime_router
from app.interaction.adapters.persistence import SqlAlchemyInteractionMessageRepository
from app.interaction.application import InteractionService
from app.interaction.application.realtime import RealtimeChatService
from app.knowledge.application.embedding_runtime import SemanticEmbeddingRuntime
from app.models.runtime_service import LocalInferenceService


def register_interaction_module(app: FastAPI) -> None:
    context = app.state.context
    repository = SqlAlchemyInteractionMessageRepository(context.database)
    service = InteractionService(context.event_bus, repository)
    model_runtime = context.services.get("model_runtime")
    knowledge_service = context.services.get("knowledge")
    embedding_runtime = getattr(knowledge_service, "embedding_runtime", None)
    realtime_service = RealtimeChatService(
        context.event_bus,
        service,
        settings=context.settings,
        model_runtime=model_runtime if isinstance(model_runtime, LocalInferenceService) else None,
        embedding_runtime=embedding_runtime if isinstance(embedding_runtime, SemanticEmbeddingRuntime) else None,
    )
    register_service(app, "interaction", service)
    register_service(app, "interaction_realtime", realtime_service)
    register_module_group(
        app,
        "interaction",
        ("interaction",),
        routers=(interaction_router, interaction_realtime_router),
    )
    register_interaction_event_handlers(app)