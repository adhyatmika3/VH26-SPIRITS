import uuid
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.canonical_alert import CanonicalAlert
    from app.models.decision_record import DecisionRecord
    from app.models.notification_record import NotificationRecord
    from app.models.escalation_record import EscalationRecord


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    incident_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="OPEN",
        index=True
    )
    priority: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="MEDIUM",
        index=True
    )
    alert_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unique_alerts_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_storm: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Phase 3 Lifecycle & Escalation Tracking
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
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

    # Relationships
    alerts: Mapped[List["CanonicalAlert"]] = relationship(
        "CanonicalAlert",
        back_populates="incident",
        lazy="selectin"
    )
    decisions: Mapped[List["DecisionRecord"]] = relationship(
        "DecisionRecord",
        back_populates="incident",
        lazy="selectin"
    )
    notifications: Mapped[List["NotificationRecord"]] = relationship(
        "NotificationRecord",
        back_populates="incident",
        lazy="selectin"
    )
    escalations: Mapped[List["EscalationRecord"]] = relationship(
        "EscalationRecord",
        back_populates="incident",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Incident {self.incident_number} status={self.status} priority={self.priority} service={self.service}>"

