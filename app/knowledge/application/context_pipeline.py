from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
from math import sqrt
import re

from app.knowledge.application.engram_directory import EngramDirectory
from app.knowledge.application.embedding_runtime import SemanticEmbeddingRuntime
from app.knowledge.application.ports import EngramRepositoryPort, KnowledgeRepositoryPort
from app.knowledge.domain import Identity, KnowledgeEntry


def _normalize_text(raw_text: str) -> str:
    text = raw_text.lower()
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`{1,3}", " ", text)
    text = re.sub(r"[*_~#>{2,}|]", " ", text)
    return " ".join(text.split())


def _tokenize(raw_text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9áéíóúñ]+", raw_text.lower()):
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tuple(tokens)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _excerpt(text: str, keywords: tuple[str, ...], *, limit: int = 480) -> str:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    for keyword in keywords:
        if not keyword:
            continue
        index = lowered.find(keyword.lower())
        if index >= 0:
            start = max(0, index - 120)
            end = min(len(cleaned), index + len(keyword) + 360)
            excerpt = cleaned[start:end]
            if start > 0:
                excerpt = f"...{excerpt}"
            if end < len(cleaned):
                excerpt = f"{excerpt}..."
            return excerpt

    excerpt = cleaned[:limit]
    if len(cleaned) > limit:
        excerpt = f"{excerpt}..."
    return excerpt


def _identity_hint_bonus(identity: Identity, mentions: tuple[str, ...]) -> float:
    if not mentions:
        return 0.0

    haystack = " ".join(
        [
            identity.name,
            identity.avatar,
            identity.intellectual_profile,
            identity.behavior_prompt,
            identity.meta_rule,
            identity.backstory,
            " ".join(identity.dialogue_examples),
        ]
    ).lower()

    score = 0.0
    for mention in mentions:
        mention_lower = mention.lower()
        if mention_lower == identity.name.lower() or mention_lower in identity.name.lower():
            score += 10.0
        elif mention_lower in haystack:
            score += 4.0
    return score


@dataclass(frozen=True)
class QueryRoutingPlan:
    intent: str
    include_source_types: tuple[str, ...] | None
    identity_mentions: tuple[str, ...]
    keywords: tuple[str, ...]
    limit: int = 5

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "include_source_types": list(self.include_source_types) if self.include_source_types is not None else None,
            "identity_mentions": list(self.identity_mentions),
            "keywords": list(self.keywords),
            "limit": self.limit,
        }


@dataclass(frozen=True)
class ContextMatch:
    source_type: str
    source_id: str
    label: str
    score: float
    excerpt: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "label": self.label,
            "score": self.score,
            "excerpt": self.excerpt,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RetrievalOutcome:
    route: QueryRoutingPlan
    knowledge_matches: tuple[ContextMatch, ...]
    engram_matches: tuple[ContextMatch, ...]


@dataclass(frozen=True)
class ContextPack:
    route: QueryRoutingPlan
    identity: Identity
    raw_text: str
    history: str = ""
    parent_context: str = ""
    child_context: str = ""
    knowledge_matches: tuple[ContextMatch, ...] = ()
    engram_matches: tuple[ContextMatch, ...] = ()

    def render(self) -> str:
        return "\n".join(part for part in (self.parent_context, self.child_context) if part.strip())

    @property
    def is_empty(self) -> bool:
        return not self.render().strip()

    def to_trace_dict(self) -> dict[str, object]:
        rendered = self.render()
        return {
            "intent": self.route.intent,
            "source_types": list(self.route.include_source_types) if self.route.include_source_types else [],
            "identity_name": self.identity.name,
            "identity_mentions": list(self.route.identity_mentions),
            "keywords": list(self.route.keywords),
            "knowledge_count": len(self.knowledge_matches),
            "engram_count": len(self.engram_matches),
            "raw_chars": len(self.raw_text),
            "history_chars": len(self.history),
            "parent_chars": len(self.parent_context),
            "child_chars": len(self.child_context),
            "rendered_chars": len(rendered),
            "is_empty": not rendered.strip(),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route.to_dict(),
            "identity": self.identity.as_dict(),
            "raw_text": self.raw_text,
            "history": self.history,
            "parent_context": self.parent_context,
            "child_context": self.child_context,
            "context_text": self.render(),
            "knowledge_matches": [match.to_dict() for match in self.knowledge_matches],
            "engram_matches": [match.to_dict() for match in self.engram_matches],
            "trace": self.to_trace_dict(),
        }


@dataclass(frozen=True)
class ContextPreview:
    route: QueryRoutingPlan
    identity: Identity
    context_pack: ContextPack
    prompt: str

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route.to_dict(),
            "identity": self.identity.as_dict(),
            "context_pack": self.context_pack.to_dict(),
            "context_text": self.context_pack.render(),
            "prompt": self.prompt,
        }


class ContextQueryRouter:
    _semantic_prototypes: dict[str, tuple[str, ...]] = {
        "identity": (
            "quien eres",
            "como te llamas",
            "perfil del asistente",
            "habla de tu identidad",
        ),
        "knowledge": (
            "busca contexto en documentos",
            "resume el documento",
            "recupera memoria",
            "necesito fuentes",
        ),
        "conversational": (
            "como sigues",
            "que opinas",
            "hablemos",
            "charla breve",
        ),
        "greeting": (
            "hola",
            "buenas",
            "saludo breve",
        ),
        "mixed": (
            "consulta general con contexto",
            "mezcla de charla y soporte",
            "quiero contexto y opinion",
        ),
    }

    def __init__(self, embedding_runtime: SemanticEmbeddingRuntime | None = None) -> None:
        self.embedding_runtime = embedding_runtime or SemanticEmbeddingRuntime()

    _identity_patterns = (
        r"\bengram\b",
        r"\bidentity\b",
        r"\bidentidad\b",
        r"\bpersona\b",
        r"\bperfil\b",
        r"\brol\b",
        r"@",
    )
    _knowledge_patterns = (
        r"\bknowledge\b",
        r"\bconoc",
        r"\bmemoria\b",
        r"\brecuerd",
        r"\bcontexto\b",
        r"\bpdf\b",
        r"\bdocument",
        r"\barchivo\b",
        r"\bmanual\b",
        r"\btexto\b",
        r"\bfragment",
        r"\bfuente\b",
        r"\bnota\b",
        r"\bitem\b",
    )

    def resolve_intent(self, raw_text: str) -> str:
        semantic_intent = self.embedding_runtime.classify_by_prototypes(raw_text, self._semantic_prototypes)
        if semantic_intent in {"identity", "knowledge"}:
            return semantic_intent
        if semantic_intent in {"greeting", "conversational"}:
            return "mixed"

        normalized = _normalize_text(raw_text)
        identity_hits = any(re.search(pattern, normalized) for pattern in self._identity_patterns)
        knowledge_hits = any(re.search(pattern, normalized) for pattern in self._knowledge_patterns)

        if identity_hits and knowledge_hits:
            return "mixed"
        if identity_hits:
            return "identity"
        if knowledge_hits:
            return "knowledge"
        return "mixed"

    def resolve(self, raw_text: str, *, limit: int = 5) -> QueryRoutingPlan:
        safe_limit = max(1, limit)
        intent = self.resolve_intent(raw_text)
        keywords = _tokenize(raw_text)
        identity_mentions = tuple(dict.fromkeys(match.group(1) for match in re.finditer(r"@([\w-]+)", raw_text)))

        if intent == "identity":
            include_source_types: tuple[str, ...] | None = ("engrams",)
        elif intent == "knowledge":
            include_source_types = ("knowledge_entries",)
        else:
            include_source_types = None

        return QueryRoutingPlan(
            intent=intent,
            include_source_types=include_source_types,
            identity_mentions=identity_mentions,
            keywords=keywords,
            limit=safe_limit,
        )


class ContextRetrieverRuntime:
    def __init__(
        self,
        knowledge_repository: KnowledgeRepositoryPort,
        engram_repository: EngramRepositoryPort | None = None,
        embedding_runtime: SemanticEmbeddingRuntime | None = None,
    ) -> None:
        self.knowledge_repository = knowledge_repository
        self.engram_repository = engram_repository
        self.embedding_runtime = embedding_runtime or SemanticEmbeddingRuntime()

    def retrieve(self, raw_text: str, route: QueryRoutingPlan) -> RetrievalOutcome:
        query_tokens = _tokenize(raw_text)
        query_embedding = self.embedding_runtime.embed_text(raw_text)
        legacy_query_embedding = self.embedding_runtime.legacy_embed_text(raw_text)
        source_types = route.include_source_types or ("knowledge_entries", "engrams")

        knowledge_matches: tuple[ContextMatch, ...] = ()
        engram_matches: tuple[ContextMatch, ...] = ()

        if "knowledge_entries" in source_types:
            knowledge_matches = self._retrieve_knowledge(query_tokens, query_embedding, legacy_query_embedding, route)

        if "engrams" in source_types and self.engram_repository:
            engram_matches = self._retrieve_engrams(query_tokens, route)

        return RetrievalOutcome(route=route, knowledge_matches=knowledge_matches, engram_matches=engram_matches)

    def _retrieve_knowledge(
        self,
        query_tokens: tuple[str, ...],
        query_embedding: list[float],
        legacy_query_embedding: list[float],
        route: QueryRoutingPlan,
    ) -> tuple[ContextMatch, ...]:
        entries = self.knowledge_repository.list_all()
        matches = [self._score_knowledge_entry(entry, query_tokens, query_embedding, legacy_query_embedding) for entry in entries]
        ranked = sorted(matches, key=lambda match: (match.score, match.metadata.get("created_at", ""), match.label), reverse=True)
        ranked = list(self._rerank_knowledge_diversity(ranked, route.limit))

        if not any(match.score > 0 for match in ranked):
            recent_entries = self.knowledge_repository.list_recent(route.limit)
            return tuple(
                ContextMatch(
                    source_type="knowledge_entries",
                    source_id=str(entry.id),
                    label=entry.title,
                    score=0.0,
                    excerpt=_excerpt(f"{entry.title} {entry.content}", query_tokens),
                    metadata={"tags": list(entry.tags), "created_at": entry.created_at.isoformat() if entry.created_at else None},
                )
                for entry in recent_entries
            )

        return tuple(ranked[: route.limit])

    def _rerank_knowledge_diversity(self, ranked: list[ContextMatch], limit: int) -> tuple[ContextMatch, ...]:
        selected: list[ContextMatch] = []
        seen_docs: set[str] = set()
        for match in ranked:
            document_id = str(match.metadata.get("document_id") or "")
            if document_id and document_id in seen_docs and len(selected) >= max(1, limit // 2):
                continue
            selected.append(match)
            if document_id:
                seen_docs.add(document_id)
            if len(selected) >= limit:
                break
        if len(selected) < limit:
            for match in ranked:
                if match in selected:
                    continue
                selected.append(match)
                if len(selected) >= limit:
                    break
        return tuple(selected)

    def _retrieve_engrams(self, query_tokens: tuple[str, ...], route: QueryRoutingPlan) -> tuple[ContextMatch, ...]:
        identities = self.engram_repository.list_all() if self.engram_repository else []
        matches = [self._score_identity(identity, query_tokens, route.identity_mentions) for identity in identities]
        ranked = sorted(matches, key=lambda match: (match.score, match.metadata.get("created_at", ""), match.label), reverse=True)

        if not any(match.score > 0 for match in ranked):
            recent_identities = self.engram_repository.list_recent(route.limit) if self.engram_repository else []
            return tuple(
                ContextMatch(
                    source_type="engrams",
                    source_id=str(identity.id),
                    label=identity.name,
                    score=0.0,
                    excerpt=_excerpt(
                        " ".join(
                            [
                                identity.name,
                                identity.intellectual_profile,
                                identity.behavior_prompt,
                                identity.meta_rule,
                                identity.backstory,
                                " ".join(identity.dialogue_examples),
                            ]
                        ),
                        query_tokens,
                    ),
                    metadata={"hint_handle": identity.hint_handle(), "created_at": identity.created_at.isoformat() if identity.created_at else None},
                )
                for identity in recent_identities
            )

        return tuple(ranked[: route.limit])

    def _score_knowledge_entry(
        self,
        entry: KnowledgeEntry,
        query_tokens: tuple[str, ...],
        query_embedding: list[float],
        legacy_query_embedding: list[float],
    ) -> ContextMatch:
        title_tokens = set(_tokenize(entry.title))
        content_tokens = set(_tokenize(entry.content))
        tag_tokens = set(_tokenize(" ".join(entry.tags)))
        score = 0.0

        for token in query_tokens:
            if token in title_tokens:
                score += 4.0
            if token in tag_tokens:
                score += 3.0
            if token in content_tokens:
                score += 1.0

        token_union = title_tokens | tag_tokens | content_tokens
        if query_tokens:
            coverage = len([token for token in query_tokens if token in token_union]) / len(query_tokens)
            score += coverage * 3.0

        embedding_score = self._embedding_score(entry.embedding, query_embedding, legacy_query_embedding)
        score += embedding_score * 4.0

        if entry.source_type == "document":
            score += 0.5
        elif entry.source_type == "document_chunk":
            score += 1.5
        elif entry.source_type == "document_image":
            score += 1.0

        label = entry.document_title or entry.title
        if entry.source_type == "document_chunk":
            page_label = f"p{entry.page_number}" if entry.page_number is not None else "p?"
            chunk_label = f"#{(entry.chunk_index or 0) + 1}"
            label = f"{label} [{page_label} {chunk_label}]"
        elif entry.source_type == "document":
            label = f"{label} [document]"

        excerpt = _excerpt(f"{entry.title}. {entry.content}", query_tokens)
        return ContextMatch(
            source_type=entry.source_type if entry.source_type != "manual" else "knowledge_entries",
            source_id=str(entry.id),
            label=label,
            score=score,
            excerpt=excerpt,
            metadata={
                "tags": list(entry.tags),
                "source_type": entry.source_type,
                "source_uri": entry.source_uri,
                "document_id": entry.document_id,
                "document_title": entry.document_title,
                "page_number": entry.page_number,
                "chunk_index": entry.chunk_index,
                "chunk_count": entry.chunk_count,
                "source_chars": entry.source_chars,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            },
        )

    @staticmethod
    def _embedding_score(entry_embedding: list[float], query_embedding: list[float], legacy_query_embedding: list[float]) -> float:
        if not entry_embedding:
            return 0.0
        if len(entry_embedding) == len(query_embedding):
            return _cosine_similarity(query_embedding, list(entry_embedding))
        if len(entry_embedding) == len(legacy_query_embedding):
            return _cosine_similarity(legacy_query_embedding, list(entry_embedding))
        return 0.0

    def _score_identity(
        self,
        identity: Identity,
        query_tokens: tuple[str, ...],
        mentions: tuple[str, ...],
    ) -> ContextMatch:
        title_tokens = set(_tokenize(identity.name))
        body_tokens = set(
            _tokenize(
                " ".join(
                    [
                        identity.intellectual_profile,
                        identity.behavior_prompt,
                        identity.meta_rule,
                        identity.backstory,
                        " ".join(identity.dialogue_examples),
                    ]
                )
            )
        )
        score = _identity_hint_bonus(identity, mentions)

        for token in query_tokens:
            if token in title_tokens:
                score += 4.0
            if token in body_tokens:
                score += 1.0

        excerpt = _excerpt(
            " ".join(
                [
                    identity.name,
                    identity.intellectual_profile,
                    identity.behavior_prompt,
                    identity.meta_rule,
                    identity.backstory,
                    " ".join(identity.dialogue_examples),
                ]
            ),
            query_tokens,
        )
        return ContextMatch(
            source_type="engrams",
            source_id=str(identity.id),
            label=identity.name,
            score=score,
            excerpt=excerpt,
            metadata={
                "hint_handle": identity.hint_handle(),
                "created_at": identity.created_at.isoformat() if identity.created_at else None,
            },
        )


class ContextAssembler:
    def assemble(
        self,
        retrieval: RetrievalOutcome,
        identity: Identity,
        raw_text: str,
        *,
        history: str = "",
    ) -> ContextPack:
        parent_context = self._build_parent_context(retrieval)
        child_context = self._build_child_context(retrieval, history=history)
        return ContextPack(
            route=retrieval.route,
            identity=identity,
            raw_text=raw_text,
            history=history,
            parent_context=parent_context,
            child_context=child_context,
            knowledge_matches=retrieval.knowledge_matches,
            engram_matches=retrieval.engram_matches,
        )

    def _build_parent_context(self, retrieval: RetrievalOutcome) -> str:
        lines: list[str] = [
            "[CONTEXT ROUTING]",
            f"intent: {retrieval.route.intent}",
            f"keywords: {', '.join(retrieval.route.keywords) if retrieval.route.keywords else 'none'}",
        ]
        if retrieval.route.identity_mentions:
            lines.append(f"identity_mentions: {', '.join(retrieval.route.identity_mentions)}")

        if retrieval.knowledge_matches:
            lines.append("")
            lines.append("[RELEVANT KNOWLEDGE]")
            for match in retrieval.knowledge_matches:
                lines.append(f"- {match.label} (score={match.score:.2f})")
                if match.excerpt:
                    lines.append(f"  {match.excerpt}")

        return "\n".join(lines).strip()

    def _build_child_context(self, retrieval: RetrievalOutcome, *, history: str = "") -> str:
        lines: list[str] = []
        if retrieval.engram_matches:
            lines.append("[RELEVANT ENGRAMS]")
            for match in retrieval.engram_matches:
                lines.append(f"- {match.label} (@{match.metadata.get('hint_handle', '').lstrip('@')}) (score={match.score:.2f})")
                if match.excerpt:
                    lines.append(f"  {match.excerpt}")

        if history.strip():
            if lines:
                lines.append("")
            lines.append("[HISTORY]")
            lines.append(history.strip())

        return "\n".join(lines).strip()


class PromptComposer:
    def build_prompt(
        self,
        *,
        identity: Identity,
        user_input: str,
        history: str,
        context_pack: ContextPack,
    ) -> str:
        system_parts = [
            "<|im_start|>system",
            f"Identity: {identity.name}",
            f"Profile: {identity.intellectual_profile}",
            f"Behavior prompt: {identity.behavior_prompt}".rstrip(),
            f"Meta rule: {identity.meta_rule}".rstrip(),
            f"Context intent: {context_pack.route.intent}",
        ]

        rendered_context = context_pack.render()
        if rendered_context:
            system_parts.append("Context:")
            system_parts.append(rendered_context)

        if history.strip():
            system_parts.append("History:")
            system_parts.append(history.strip())

        system_parts.append("<|im_end|>")
        system_prompt = "\n".join(system_parts)

        return (
            f"{system_prompt}\n"
            f"<|im_start|>user\n{user_input.strip()}<|im_end|>\n"
            f"<|im_start|>{identity.name}:"
        )


class KnowledgeContextPipeline:
    def __init__(
        self,
        knowledge_repository: KnowledgeRepositoryPort,
        engram_repository: EngramRepositoryPort | None,
        directory: EngramDirectory,
        embedding_runtime: SemanticEmbeddingRuntime | None = None,
    ) -> None:
        self.router = ContextQueryRouter(embedding_runtime=embedding_runtime)
        self.retriever = ContextRetrieverRuntime(knowledge_repository, engram_repository, embedding_runtime=embedding_runtime)
        self.assembler = ContextAssembler()
        self.composer = PromptComposer()
        self.directory = directory

    def route_query(self, raw_text: str, *, limit: int = 5) -> QueryRoutingPlan:
        return self.router.resolve(raw_text, limit=limit)

    def build_preview(
        self,
        raw_text: str,
        *,
        limit: int = 5,
        identity_id: str | None = None,
        history: str = "",
    ) -> ContextPreview:
        route = self.route_query(raw_text, limit=limit)
        identity, cleaned_text = self.directory.resolve(raw_text, identity_id)
        retrieval = self.retriever.retrieve(cleaned_text, route)
        context_pack = self.assembler.assemble(retrieval, identity, cleaned_text, history=history)
        prompt = self.composer.build_prompt(
            identity=identity,
            user_input=cleaned_text,
            history=history,
            context_pack=context_pack,
        )
        return ContextPreview(route=route, identity=identity, context_pack=context_pack, prompt=prompt)