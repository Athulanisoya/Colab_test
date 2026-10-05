"""Incident projection, visibility filtering and lifecycle records."""
from copy import deepcopy
from sqlalchemy import select

from backend.models.incident import Assignment, Incident, StatusHistory
from backend.utils.permissions import active_assignment
from backend.utils.validators import serialize
from .notification_service import audit, notify


def serialize_incident(incident, user=None):
    data = serialize(incident)
    data["analysis"] = deepcopy(incident.analysis.result) if incident.analysis else None
    if data["analysis"] and (user is None or user.role != "admin"):
        # Duplicate review belongs to coordinators, not other report owners.
        data["analysis"].pop("duplicate_candidates", None)
        data["analysis"].pop("duplicates", None)
        data["analysis"].pop("duplicate_ids", None)
        data["analysis"].pop("duplicate_suggestions", None)
        for step in data["analysis"].get("tool_trace", []):
            if step.get("name") == "find_duplicates":
                step.pop("output", None)
    data["clarification"] = data["analysis"].get("clarification") if data["analysis"] else None
    if user is not None and user.role == "admin":
        data["analysis_history"] = deepcopy(incident.analysis.history) if incident.analysis else []
    data["history"] = [serialize(row) for row in incident.history]
    assignment = active_assignment(incident)
    data["assignment"] = {**serialize(assignment), "team_name": assignment.team.name, "team_type": assignment.team.team_type} if assignment else None
    return data


def status_change(db, incident, status, user, note=""):
    incident.status = status
    db.add(StatusHistory(incident_id=incident.id, status=status, note=note, actor_id=user.id))
    audit(db, user, "incident.status", "incident", incident.id, {"status": status, "note": note})
    notify(db, incident.user_id, "Report status updated", f"{incident.reference}: {status.replace('_', ' ')}. {note}", incident.id)


def incident_query(user):
    query = select(Incident)
    if user.role == "citizen":
        return query.where(Incident.user_id == user.id)
    if user.role == "response_team":
        return query.join(Assignment).where(Assignment.team_id == user.team_id, Assignment.active.is_(True))
    return query
