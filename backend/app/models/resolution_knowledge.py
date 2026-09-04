import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import String, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ResolutionKnowledge(Base):
    __tablename__ = "resolution_knowledge"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    fingerprint: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True
    )
    alert_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    environment: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    probable_cause: Mapped[str] = mapped_column(String(1000), nullable=False)
    resolution_steps: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.90)
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="automated_analysis"  # "automated_analysis", "knowledge_base", "manual"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<ResolutionKnowledge fp={self.fingerprint[:8]} type={self.alert_type} source={self.source} confidence={self.confidence}>"
