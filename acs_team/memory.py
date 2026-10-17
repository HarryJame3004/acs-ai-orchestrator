"""ACS AI V2 Long-Term Project Memory Engine.
Powered by SQLite WAL + FTS5 full-text search.
Provides project-scoped memory categories:
- Decision memory
- Failure memory
- Knowledge memory
- Project memory
Includes automatic stale memory detection on commit progression.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from .db import DatabaseManager

logger = logging.getLogger("acs_ai.memory")


class MemoryEngine:
    """High-level memory interface for agents, planners, and reviewers."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def record_decision(
        self,
        project_id: str,
        repository_id: str,
        title: str,
        rationale: str,
        commit_sha: Optional[str] = None,
        confidence: float = 1.0,
    ) -> str:
        """Records an architectural or implementation decision."""
        mem_id = f"dec-{uuid.uuid4().hex[:8]}"
        return self.db.save_memory(
            memory_id=mem_id,
            project_id=project_id,
            repository_id=repository_id,
            memory_type="decision",
            title=title,
            content=rationale,
            source_type="agent_decision",
            source_commit=commit_sha,
            confidence=confidence,
        )

    def record_failure(
        self,
        project_id: str,
        repository_id: str,
        title: str,
        error_message: str,
        resolution: str,
        commit_sha: Optional[str] = None,
    ) -> str:
        """Records a defect, failure pattern, and its resolution to prevent repeat errors."""
        mem_id = f"fail-{uuid.uuid4().hex[:8]}"
        content = f"Error: {error_message}\nResolution: {resolution}"
        return self.db.save_memory(
            memory_id=mem_id,
            project_id=project_id,
            repository_id=repository_id,
            memory_type="failure",
            title=title,
            content=content,
            source_type="test_or_review_failure",
            source_commit=commit_sha,
        )

    def record_knowledge(
        self,
        project_id: str,
        repository_id: str,
        title: str,
        content: str,
        source_reference: Optional[str] = None,
    ) -> str:
        """Records persistent domain, framework, or architectural knowledge."""
        mem_id = f"know-{uuid.uuid4().hex[:8]}"
        return self.db.save_memory(
            memory_id=mem_id,
            project_id=project_id,
            repository_id=repository_id,
            memory_type="knowledge",
            title=title,
            content=content,
            source_type="repository_docs",
            source_reference=source_reference,
        )

    def search(
        self,
        project_id: str,
        query: str = "",
        memory_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Searches project memories using SQLite FTS5 with project isolation."""
        return self.db.search_memories(
            query=query,
            project_id=project_id,
            memory_type=memory_type,
            limit=limit,
        )

    def detect_and_mark_stale(
        self,
        project_id: str,
        repository_id: str,
        current_commit_sha: str,
    ) -> int:
        """Marks memories tied to older commits as stale to prevent hallucinating on outdated code."""
        stale_count = self.db.mark_memory_stale(
            project_id=project_id,
            repository_id=repository_id,
            commit_sha=current_commit_sha,
        )
        if stale_count > 0:
            logger.info(
                f"Marked {stale_count} memory records as stale for project '{project_id}' at commit {current_commit_sha[:8]}"
            )
        return stale_count
