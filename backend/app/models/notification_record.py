import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.decision_record import DecisionRecord
    from app.models.incident import Incident
    from app.models.canonical_alert import CanonicalAlert


class NotificationRecord(Base):
    __tablename__ = "notification_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decision_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    canonical_alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="slack", index=True)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="INITIAL",
        index=True  # INITIAL, ESCALATION, MANUAL, RESOLUTION
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="SENT",
        index=True  # SENT, FAILED, SKIPPED
    )
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict
    )
    error_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    # Relationships
    decision: Mapped[Optional["DecisionRecord"]] = relationship("DecisionRecord", back_populates="notifications")
    incident: Mapped[Optional["Incident"]] = relationship("Incident", back_populates="notifications")
    canonical_alert: Mapped[Optional["CanonicalAlert"]] = relationship("CanonicalAlert")

    def __repr__(self) -> str:
        return f"<NotificationRecord id={self.id} channel={self.channel} status={self.status} type={self.notification_type}>"
