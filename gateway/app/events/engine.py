from .rules import SnapshotCreatedRule, RevenueRule, AverageCheckRule

class EventEngine:
    def __init__(self,repository,rules=None):
        self.repository=repository
        self.rules=rules or [SnapshotCreatedRule(),RevenueRule(),AverageCheckRule()]

    def process_snapshot(self,current,previous):
        result=[]
        for rule in self.rules:
            for event in rule.evaluate(current,previous):
                self.repository.save(event); result.append(event)
        return result
