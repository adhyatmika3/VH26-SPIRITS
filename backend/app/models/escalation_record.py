import uuid
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.incident import Incident
    from app.models.canonical_alert import CanonicalAlert


class EscalationRecord(Base):
    __tablename__ = "escalation_records"
    __table_args__ = (
        UniqueConstraint("incident_id", "escalation_level", name="uq_incident_escalation_level"),
    )


    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    canonical_alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    escalation_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reason_codes: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list
    )
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="TRIGGERED",
        index=True  # TRIGGERED, ACKNOWLEDGED, RESOLVED
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="escalations")
    canonical_alert: Mapped[Optional["CanonicalAlert"]] = relationship("CanonicalAlert")

    def __repr__(self) -> str:
        return f"<EscalationRecord id={self.id} incident_id={self.incident_id} level={self.escalation_level}>"
