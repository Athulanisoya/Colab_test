from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, Assignment, Distribution, Incident, Inventory, ReliefRequest, Team
from backend.schemas import DistributionCreate, InventoryCreate, InventoryUpdate, ReliefCreate
from backend.utils.jwt import get_current_user
from backend.utils.permissions import require_admin, require_operator
from backend.services.relief_service import distribute_relief, relief_data
from backend.services.relief_service import locked_relief_request, normalize_requested_items
from backend.schemas.relief_schema import ReliefAssign, ReliefComplete
from backend.services.team_service import lock_teams, team_has_active_incident
from backend.services import active_assignment, apply_changes, audit, get_row, notify, serialize

router = APIRouter(prefix="/api", tags=["Response operations"])


@router.post("/relief/request", status_code=201)
def request_relief(body: ReliefCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "citizen":
        raise HTTPException(403, "Citizen account required for relief requests")
    if body.incident_id:
        if db.bind.dialect.name == "sqlite":
            db.rollback()
            db.execute(text("BEGIN IMMEDIATE"))
        incident = get_row(db, Incident, body.incident_id, lock=True)
        if incident.user_id != user.id:
            raise HTTPException(403, "Relief requests must link to your own incident")
        if incident.status in ("resolved", "closed"):
            raise HTTPException(409, "Submit an independent request for further assistance after case resolution")
    values = body.model_dump()
    values["items"] = normalize_requested_items(db, body.items)
    row = ReliefRequest(**values, user_id=user.id)
    db.add(row)
    db.flush()
    audit(db, user, "relief.request", "relief_request", row.id)
    notify(db, user.id, "Relief request received", f"Your request at {body.location} is awaiting coordination.", body.incident_id)
    db.commit()
    return relief_data(db, row)


@router.get("/relief/my")
def my_relief(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [relief_data(db, row) for row in db.scalars(select(ReliefRequest).where(ReliefRequest.user_id == user.id).order_by(ReliefRequest.id.desc()))]


@router.get("/relief/requests")
def relief_requests(user: User = Depends(require_operator), db: Session = Depends(get_db)):
    query = select(ReliefRequest)
    if user.role != "admin":
        team = db.get(Team, user.team_id) if user.team_id else None
        if not team or team.team_type not in ("relief", "rescue"):
            raise HTTPException(403, "Relief or rescue team permission required")
        own_incidents = select(Assignment.incident_id).where(Assignment.team_id == user.team_id, Assignment.active.is_(True))
        query = query.where(or_(ReliefRequest.assigned_team_id == user.team_id, ReliefRequest.incident_id.in_(own_incidents)))
    return [relief_data(db, row) for row in db.scalars(query.order_by(ReliefRequest.id.desc())).unique()]


@router.get("/relief/inventory")
def inventory(user: User = Depends(require_operator), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(Inventory).order_by(Inventory.id))]


@router.post("/relief/inventory", status_code=201)
def create_inventory(body: InventoryCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = Inventory(**body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "inventory.create", "inventory", row.id)
    db.commit()
    return serialize(row)


@router.put("/relief/inventory/{inventory_id}")
def update_inventory(inventory_id: int, body: InventoryUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = get_row(db, Inventory, inventory_id, lock=True)
    # Item identity is immutable once used, preserving distribution accounting.
    if ((body.item is not None and body.item.casefold() != row.item.casefold()) or
        (body.unit is not None and body.unit.casefold() != row.unit.casefold())) and db.scalar(select(Distribution.id).where(Distribution.inventory_id == inventory_id)):
        raise HTTPException(409, "Distributed inventory item names and units cannot be changed")
    apply_changes(row, body)
    audit(db, user, "inventory.update", "inventory", row.id, {"quantity": row.quantity})
    db.commit()
    return serialize(row)


@router.get("/relief/catalog")
def catalog(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"inventory_id": row.id, "item": row.item, "unit": row.unit, "quantity": row.quantity}
            for row in db.scalars(select(Inventory).order_by(Inventory.item, Inventory.unit))]


@router.post("/relief/requests/{request_id}/assign")
def assign_request(request_id: int, body: ReliefAssign, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    row = locked_relief_request(db, request_id)
    get_row(db, Team, body.team_id)
    teams = lock_teams(db, (body.team_id, row.assigned_team_id))
    team = teams[body.team_id]
    required = "rescue" if row.kind == "rescue_support" else "relief"
    if team.team_type != required:
        raise HTTPException(422, f"Select a {required} team")
    if row.status in ("fulfilled", "cancelled"):
        raise HTTPException(409, "Completed requests cannot be reassigned")
    if row.assigned_team_id == team.id:
        return relief_data(db, row)
    linked_assignment = active_assignment(db.get(Incident, row.incident_id)) if row.incident_id else None
    if (not team.available or team_has_active_incident(db, team.id)) and not (linked_assignment and linked_assignment.team_id == team.id):
        raise HTTPException(409, "Selected team is not available")
    previous = teams.get(row.assigned_team_id)
    row.assigned_team_id = team.id
    row.status = "assigned" if row.status == "pending" else row.status
    team.available = False
    if previous:
        db.flush()
        previous.available = not team_has_active_incident(db, previous.id)
    audit(db, user, "relief.assign", "relief_request", row.id, {"team_id": team.id, "note": body.note})
    notify(db, row.user_id, "Request assigned", f"{team.name} will respond to your request.", row.incident_id)
    for member in db.scalars(select(User).where(User.team_id == team.id, User.active.is_(True))):
        notify(db, member.id, "New relief assignment", f"Request #{row.id} at {row.location}", row.incident_id)
    db.commit()
    return relief_data(db, row)


@router.post("/relief/requests/{request_id}/complete")
def complete_support(request_id: int, body: ReliefComplete, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    row = locked_relief_request(db, request_id)
    teams = lock_teams(db, (row.assigned_team_id, user.team_id))
    if row.kind != "rescue_support":
        raise HTTPException(422, "Supply requests complete through distribution accounting")
    if user.role != "admin" and (row.assigned_team_id != user.team_id or not teams.get(user.team_id) or teams[user.team_id].team_type != "rescue"):
        raise HTTPException(403, "Assigned rescue team required")
    if not row.assigned_team_id or row.status in ("fulfilled", "cancelled"):
        raise HTTPException(409, "An open assigned request is required")
    row.status = "fulfilled"
    audit(db, user, "relief.rescue_complete", "relief_request", row.id, {"note": body.note})
    notify(db, row.user_id, "Rescue support completed", body.note, row.incident_id)
    team = teams[row.assigned_team_id]
    db.flush()
    team.available = not team_has_active_incident(db, team.id)
    db.commit()
    return relief_data(db, row)


@router.post("/relief/distribution", status_code=201)
def distribute(body: DistributionCreate, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    return distribute_relief(db, user, body)


@router.get("/relief/distributions")
def distributions(user: User = Depends(require_operator), db: Session = Depends(get_db)):
    query = select(Distribution)
    if user.role != "admin":
        query = query.where(Distribution.actor_id == user.id)
    return [serialize(row) for row in db.scalars(query.order_by(Distribution.id.desc()))]
