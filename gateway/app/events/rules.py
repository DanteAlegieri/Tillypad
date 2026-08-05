from .models import Event, Snapshot
from .types import EventType, EventSeverity, EventSource

class SnapshotCreatedRule:
    def evaluate(self,current,previous):
        return [Event.create(
          snapshot_id=current.id,agent_id=current.agent_id,
          event_type=EventType.SNAPSHOT_CREATED,severity=EventSeverity.INFO,
          source=EventSource.SYSTEM,title="Получен новый снимок ресторана",
          description=f"Выручка {current.revenue:.0f} ₽, чеков {current.orders}, средний чек {current.average_check:.0f} ₽.",
          payload={"business_date":current.business_date},score=20)]

class RevenueRule:
    threshold=5
    def evaluate(self,current,previous):
        if previous is None or previous.revenue<=0:return []
        d=(current.revenue-previous.revenue)/previous.revenue*100
        if abs(d)<self.threshold:return []
        up=d>0
        return [Event.create(
          snapshot_id=current.id,agent_id=current.agent_id,
          event_type=EventType.REVENUE_GROWTH if up else EventType.REVENUE_DROP,
          severity=EventSeverity.SUCCESS if up else (EventSeverity.CRITICAL if d<=-20 else EventSeverity.WARNING),
          source=EventSource.FINANCE,
          title="Выручка выросла" if up else "Выручка снизилась",
          description=f"Изменение к предыдущему снимку: {d:+.1f}%.",
          payload={"current":current.revenue,"previous":previous.revenue,"delta_percent":round(d,2)},
          score=min(100,40+int(abs(d)*2)))]

class AverageCheckRule:
    threshold=5
    def evaluate(self,current,previous):
        if previous is None or previous.average_check<=0:return []
        d=(current.average_check-previous.average_check)/previous.average_check*100
        if abs(d)<self.threshold:return []
        up=d>0
        return [Event.create(
          snapshot_id=current.id,agent_id=current.agent_id,
          event_type=EventType.AVERAGE_CHECK_GROWTH if up else EventType.AVERAGE_CHECK_DROP,
          severity=EventSeverity.SUCCESS if up else EventSeverity.WARNING,
          source=EventSource.MARKETING,
          title="Средний чек вырос" if up else "Средний чек снизился",
          description=f"Изменение среднего чека: {d:+.1f}%.",
          payload={"current":current.average_check,"previous":previous.average_check,"delta_percent":round(d,2)},
          score=min(100,35+int(abs(d)*2)))]
