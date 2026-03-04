from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from jobfinder.models.domain import NormalizedJobPosting, SearchProfile

logger = logging.getLogger(__name__)

try:
    from langchain_community.vectorstores import FAISS
except ImportError:  # pragma: no cover
    FAISS = None  # type: ignore[assignment]


class SemanticVectorIndex:
    def __init__(self, vector_dir: Path, base_url: str, embed_model: str) -> None:
        self.vector_dir = vector_dir
        self.vector_dir.mkdir(parents=True, exist_ok=True)
        self.embed_model = embed_model
        self.embedder = OllamaEmbeddings(model=embed_model, base_url=base_url)

    def score_jobs(
        self,
        run_id: str,
        profile: SearchProfile,
        jobs: list[NormalizedJobPosting],
    ) -> dict[str, float]:
        if not jobs or FAISS is None:
            return {job.fingerprint(): 0.0 for job in jobs}

        docs = [
            Document(
                page_content=f"{job.title}\n{job.location_text}\n{job.description_text[:2000]}",
                metadata={"fingerprint": job.fingerprint()},
            )
            for job in jobs
        ]
        query = " ; ".join(
            [*profile.target_roles, *profile.role_synonyms, *profile.required_skills, *profile.locations]
        )
        scores = {job.fingerprint(): 0.0 for job in jobs}

        try:
            vectorstore = FAISS.from_documents(docs, self.embedder)
            index_path = self.vector_dir / run_id
            vectorstore.save_local(str(index_path))

            raw_results = vectorstore.similarity_search_with_relevance_scores(query, k=len(jobs))
            for doc, relevance in raw_results:
                fingerprint = doc.metadata.get("fingerprint", "")
                if not fingerprint:
                    continue
                mapped = max(0.0, min(1.0, float(relevance))) * 100.0
                scores[fingerprint] = max(scores.get(fingerprint, 0.0), mapped)
        except Exception as exc:  # pragma: no cover - best effort runtime reliability
            logger.warning(
                "Semantic scoring fallback due to error: %s. "
                "If this is a missing model, run: `ollama pull %s`",
                exc,
                self.embed_model,
            )

        return scores
