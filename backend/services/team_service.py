"""Team validation and atomic incident assignment."""
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import select, text, union

from backend.models.incident import Assignment, Incident
from backend.models.team import Team
from backend.models.inventory import ReliefRequest
from backend.models.user import User, utcnow
from backend.utils.jwt import aware
from backend.utils.validators import get_row
from .incident_service import serialize_incident, status_change
from .notification_service import audit, notify


def validate_team(db, team_id, required_type=None):
    if team_id is not None:
        team = get_row(db, Team, team_id)
        if required_type and team.team_type != required_type:
            raise HTTPException(422, f"Select a {required_type} team")
        return team


def lock_teams(db, team_ids):
    """Lock affected teams in a stable order before assigning or releasing work."""
    ids = {team_id for team_id in team_ids if team_id is not None}
    return {team.id: team for team in db.scalars(select(Team).where(Team.id.in_(ids))
            .order_by(Team.id).with_for_update().execution_options(populate_existing=True))}


def operational_assignments():
    """Active case work, excluding completed assignments retained for history."""
    return select(Assignment).join(Incident).where(
        Assignment.active.is_(True), Incident.status.notin_(["resolved", "closed"])
    )


def team_has_active_incident(db, team_id, exclude_incident_id=None):
    query = operational_assignments().where(Assignment.team_id == team_id)
    if exclude_incident_id is not None:
        query = query.where(Assignment.incident_id != exclude_incident_id)
    return db.scalar(query.limit(1)) is not None or db.scalar(select(ReliefRequest.id).where(ReliefRequest.assigned_team_id == team_id, ReliefRequest.status.notin_(["fulfilled", "cancelled"])).limit(1)) is not None


def operational_team_ids():
    return union(operational_assignments().with_only_columns(Assignment.team_id),
        select(ReliefRequest.assigned_team_id).where(ReliefRequest.assigned_team_id.is_not(None), ReliefRequest.status.notin_(["fulfilled", "cancelled"])))


def available_team_query():
    busy_team_ids = operational_team_ids()
    return select(Team).where(Team.available.is_(True), Team.id.not_in(busy_team_ids))


def assignment_history(db, team_id):
    """Project only this team's own work; never expose a later team's case data."""
    rows = db.execute(
        select(Assignment, Incident).join(Incident)
        .where(Assignment.team_id == team_id).order_by(Assignment.id.desc())
    )
    history = []
    for assignment, incident in rows:
        assigned_at = aware(assignment.created_at).astimezone(timezone.utc)
        later_assignments = [aware(row.created_at) for row in incident.assignments
                             if row.id > assignment.id]
        review_times = [aware(row.created_at) for row in incident.history
                        if row.status == "under_review" and aware(row.created_at) >= assigned_at]
        boundaries = later_assignments + review_times
        release_at = min(boundaries) if boundaries and not assignment.active else None
        own_events = [row for row in incident.history
                      if aware(row.created_at) >= assigned_at
                      and (release_at is None or aware(row.created_at) < release_at)]
        completed = next((aware(row.created_at) for row in own_events
                          if row.status == "resolved"), None)
        last_status = own_events[-1].status if own_events else "team_assigned"
        history.append({
            "assignment_id": assignment.id,
            "incident_id": incident.id,
            "reference": incident.reference,
            "assigned_at": assigned_at.isoformat(),
            "ended_at": (completed or release_at).astimezone(timezone.utc).isoformat() if completed or release_at else None,
            "assignment_status": "completed" if completed else "active" if assignment.active else "released",
            "last_status": last_status,
        })
    return history


def assign_incident_team(db, user, body):
    # SQLite has no row-level FOR UPDATE; acquire its write lock before validating availability.
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    incident = get_row(db, Incident, body.incident_id, lock=True)
    team = get_row(db, Team, body.team_id, lock=True)
    if incident.status != "under_review":
        raise HTTPException(409, "Administrator review is required before assignment")
    if incident.verified is not True and team.team_type != "investigation":
        raise HTTPException(409, "Unverified reports must be assigned to investigation first")
    if not team.available or team_has_active_incident(db, team.id):
        raise HTTPException(409, "Selected team is not available")
    for existing in incident.assignments:
        existing.active = False
        existing.ended_at = utcnow()
    db.add(Assignment(incident_id=incident.id, team_id=team.id, assigned_by=user.id, note=body.note))
    team.available = False
    status_change(db, incident, "team_assigned", user, body.note or f"Assigned to {team.name}")
    audit(db, user, "team.assign", "incident", incident.id, {"team_id": team.id})
    for member_id in db.scalars(select(User.id).where(User.team_id == team.id, User.active.is_(True))):
        notify(db, member_id, "New assignment", f"{incident.reference}: {incident.location}", incident.id)
    db.commit()
    db.refresh(incident)
    return serialize_incident(incident, user)
