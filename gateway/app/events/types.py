from enum import StrEnum

class EventType(StrEnum):
    SNAPSHOT_CREATED="snapshot_created"
    REVENUE_GROWTH="revenue_growth"
    REVENUE_DROP="revenue_drop"
    AVERAGE_CHECK_GROWTH="average_check_growth"
    AVERAGE_CHECK_DROP="average_check_drop"

class EventSeverity(StrEnum):
    INFO="info"
    SUCCESS="success"
    WARNING="warning"
    CRITICAL="critical"

class EventSource(StrEnum):
    MANAGER="manager"
    OPERATIONS="operations"
    MARKETING="marketing"
    TECHNOLOGY="technology"
    FINANCE="finance"
    DELIVERY="delivery"
    SYSTEM="system"

class EventStatus(StrEnum):
    NEW="new"
    ACTIVE="active"
    ACKNOWLEDGED="acknowledged"
    DONE="done"
    ARCHIVED="archived"
