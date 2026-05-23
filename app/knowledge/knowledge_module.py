from fastapi import FastAPI

from app.core.module_registry import register_module_group, register_service
from app.knowledge.adapters import register_knowledge_event_handlers
from app.knowledge.adapters.persistence import SqlAlchemyEngramRepository, SqlAlchemyKnowledgeRepository
from app.knowledge.adapters.api import router as knowledge_router
from app.knowledge.application import KnowledgeService


def register_knowledge_module(app: FastAPI) -> None:
    context = app.state.context
    repository = SqlAlchemyKnowledgeRepository(context.database)
    engram_repository = SqlAlchemyEngramRepository(context.database)
    service = KnowledgeService(
        repository=repository,
        event_bus=context.event_bus,
        engram_repository=engram_repository,
        embedding_model_dir=context.settings.embedding_model_dir,
    )
    register_service(app, "knowledge", service)
    register_module_group(app, "knowledge", ("knowledge",), routers=(knowledge_router,))
    register_knowledge_event_handlers(app)