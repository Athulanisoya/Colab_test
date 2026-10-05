"""Role gates and ownership or assignment authorization."""
from fastapi import Depends, HTTPException

from backend.models.user import User
from .jwt import get_current_user


def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator permission required")
    return user


def require_operator(user: User = Depends(get_current_user)):
    if user.role not in ("admin", "response_team"):
        raise HTTPException(403, "Response team permission required")
    return user


def active_assignment(incident):
    return next((row for row in reversed(incident.assignments) if row.active), None)


def can_read_incident(user, incident):
    assignment = active_assignment(incident)
    return user.role == "admin" or incident.user_id == user.id or (user.role == "response_team" and assignment and assignment.team_id == user.team_id)


def require_incident_access(user, incident):
    if not can_read_incident(user, incident):
        raise HTTPException(403, "This report belongs to another user or team")


def require_assigned_team(user, incident):
    assignment = active_assignment(incident)
    if user.role != "admin" and not (user.role == "response_team" and assignment and assignment.team_id == user.team_id):
        raise HTTPException(403, "Only the assigned team may update this incident")
