import uuid
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.canonical_alert import CanonicalAlert
    from app.models.incident import Incident
    from app.models.notification_record import NotificationRecord


class DecisionRecord(Base):
    __tablename__ = "decision_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    canonical_alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    decision: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True  # NOTIFY, SUPPRESS, ESCALATE
    )
    reason_codes: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list
    )
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    context_snapshot: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    processing_time_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    # Relationships
    canonical_alert: Mapped[Optional["CanonicalAlert"]] = relationship("CanonicalAlert")
    incident: Mapped[Optional["Incident"]] = relationship("Incident", back_populates="decisions")
    notifications: Mapped[List["NotificationRecord"]] = relationship("NotificationRecord", back_populates="decision")

    def __repr__(self) -> str:
        return f"<DecisionRecord id={self.id} decision={self.decision} incident_id={self.incident_id}>"
