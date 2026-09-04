from typing import List, Optional
from pydantic import BaseModel, Field


class AnalyticsOverviewResponse(BaseModel):
    total_alerts: int = Field(..., description="Total count of alerts received")
    processed_alerts: int = Field(..., description="Total count of alerts processed through intelligence pipeline")
    suppressed_alerts: int = Field(..., description="Total count of alerts suppressed")
    notified_alerts: int = Field(..., description="Total count of alerts approved for notification")
    escalated_alerts: int = Field(..., description="Total count of alerts escalated")
    suppression_rate: float = Field(..., description="Percentage of alerts suppressed")
    notification_rate: float = Field(..., description="Percentage of alerts notified")
    escalation_rate: float = Field(..., description="Percentage of alerts escalated")
    alert_reduction: int = Field(..., description="Absolute count of alerts suppressed from waking operators")
    average_processing_time_ms: float = Field(..., description="Average processing latency in milliseconds")


class SeverityDistributionItem(BaseModel):
    severity: str
    count: int
    percentage: float


class SourceDistributionItem(BaseModel):
    source: str
    count: int
    percentage: float


class ServiceDistributionItem(BaseModel):
    service: str
    count: int
    percentage: float


class NoisyServiceItem(BaseModel):
    service: str
    total_alerts: int
    suppressed_count: int
    notified_count: int
    escalated_count: int
    suppression_rate: float


class TimelinePoint(BaseModel):
    timestamp: str
    received: int
    suppressed: int
    notified: int
    escalated: int


class DecisionDistributionResponse(BaseModel):
    suppressed: int
    notified: int
    escalated: int
    total: int
