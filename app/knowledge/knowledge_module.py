from fastapi import FastAPI

from app.core.module_registry import register_module_group, register_service
from app.knowledge.adapters import register_knowledge_event_handlers
from app.knowledge.adapters.persistence import (
    SqlAlchemyAffectiveStateRepository,
    SqlAlchemyEngramRepository,
    SqlAlchemyKnowledgeRepository,
)
from app.knowledge.adapters.api import router as knowledge_router
from app.knowledge.application import KnowledgeService
from app.knowledge.application.ingest_jobs import IngestJobRegistry


def register_knowledge_module(app: FastAPI) -> None:
    context = app.state.context
    repository = SqlAlchemyKnowledgeRepository(context.database)
    engram_repository = SqlAlchemyEngramRepository(context.database)
    affective_state_repository = SqlAlchemyAffectiveStateRepository(context.database)
    service = KnowledgeService(
        repository=repository,
        event_bus=context.event_bus,
        engram_repository=engram_repository,
        embedding_model_dir=context.settings.embedding_model_dir,
        ollama_embedding_base_url=context.settings.ollama_embedding_base_url,
        ollama_embedding_model=context.settings.ollama_embedding_model,
        ai_model_dir=context.settings.ai_model_dir,
        tokenizer_model_path=context.settings.tokenizer_model_path,
        affective_state_repository=affective_state_repository,
    )
    register_service(app, "knowledge", service)
    register_service(app, "knowledge_ingest_jobs", IngestJobRegistry())
    register_module_group(app, "knowledge", ("knowledge",), routers=(knowledge_router,))
    register_knowledge_event_handlers(app)