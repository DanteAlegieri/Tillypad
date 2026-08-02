def serialize_event(event):
    return event.to_dict()

def serialize_events(events):
    return [event.to_dict() for event in events]
