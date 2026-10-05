"""Transactional audit records and user notifications."""
from backend.models.user import AuditLog, Notification


def audit(db, user, action, entity_type, entity_id=None, detail=None):
    db.add(AuditLog(actor_id=user.id if user else None, action=action, entity_type=entity_type, entity_id=entity_id, detail=detail or {}))


def notify(db, user_id, title, message, incident_id=None):
    db.add(Notification(user_id=user_id, title=title, message=message, incident_id=incident_id))
