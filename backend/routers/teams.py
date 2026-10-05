from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, Team, Shelter, TeamMember, Assignment, Incident, utcnow
from backend.schemas import AssignTeam, TeamCreate, TeamUpdate
from backend.schemas.team_schema import TaskAcceptance
from backend.utils.jwt import get_current_user
from backend.utils.permissions import require_admin, require_operator
from backend.services.team_service import assign_incident_team, assignment_history, available_team_query, team_has_active_incident
from backend.services import apply_changes, audit, get_row, serialize
from backend.services.incident_service import status_change, serialize_incident
from backend.utils.permissions import require_assigned_team

router = APIRouter(prefix="/api", tags=["Response operations"])


@router.get("/teams")
def teams(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(Team).order_by(Team.id))]


@router.get("/teams/available")
def available_teams(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(available_team_query().order_by(Team.id))]


@router.get("/teams/history")
def task_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "response_team" or user.team_id is None:
        raise HTTPException(403, "Response team account required for task history")
    return assignment_history(db, user.team_id)


@router.post("/teams", status_code=201)
def create_team(body: TeamCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = Team(**body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "team.create", "team", row.id)
    db.commit()
    return serialize(row)


@router.put("/teams/{team_id}")
def update_team(team_id: int, body: TeamUpdate, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    row = get_row(db, Team, team_id, lock=True)
    keys = body.model_fields_set
    if user.role != "admin" and (user.team_id != team_id or keys - {"available"}):
        raise HTTPException(403, "You may update only your own team's availability")
    busy = team_has_active_incident(db, team_id)
    if busy and body.available is True:
        raise HTTPException(409, "Complete the active assignment before becoming available")
    if busy and body.team_type is not None and body.team_type != row.team_type:
        raise HTTPException(409, "Team type cannot change during an active assignment")
    if body.team_type is not None and body.team_type != row.team_type and db.scalar(select(Shelter.id).where(Shelter.team_id == row.id)):
        raise HTTPException(409, "Reassign linked shelters before changing this team's type")
    apply_changes(row, body)
    audit(db, user, "team.update", "team", row.id)
    db.commit()
    return serialize(row)


@router.post("/teams/assign")
@router.post("/admin/assign-team", include_in_schema=False)
@router.post("/investigation/assign", include_in_schema=False)
def assign_team(body: AssignTeam, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return assign_incident_team(db, user, body)


@router.post("/teams/assignments/{assignment_id}/accept")
def accept_task(assignment_id: int, body: TaskAcceptance | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.bind.dialect.name == "sqlite":
        from sqlalchemy import text
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    assignment = get_row(db, Assignment, assignment_id)
    incident = get_row(db, Incident, assignment.incident_id, lock=True)
    assignment = get_row(db, Assignment, assignment_id, lock=True)
    require_assigned_team(user, incident)
    if not assignment.active or (user.role != "admin" and assignment.team_id != user.team_id):
        raise HTTPException(403, "Current assignment permission required")
    if assignment.accepted_at:
        return serialize_incident(incident, user)
    if incident.status != "team_assigned":
        raise HTTPException(409, "Only a newly assigned task can be accepted")
    assignment.accepted_at, assignment.accepted_by = utcnow(), user.id
    status_change(db, incident, "task_accepted", user, body.note if body and body.note else "Assigned team accepted the task")
    db.commit()
    db.refresh(incident)
    return serialize_incident(incident, user)


@router.get("/teams/{team_id}/members")
def team_members(team_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "admin" and (user.role != "response_team" or user.team_id != team_id):
        raise HTTPException(403, "Team membership permission required")
    from backend.services.auth_service import serialize_user
    return [serialize_user(row) for row in db.scalars(select(User).join(TeamMember, TeamMember.user_id == User.id).where(TeamMember.team_id == team_id))]
