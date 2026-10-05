from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, Shelter, Team, ShelterOccupancy, ShelterUpdateRecord, utcnow
from backend.schemas import ShelterCreate, ShelterUpdate
from backend.utils.permissions import require_admin, require_operator
from backend.services.shelter_service import nearby_shelters, shelter_data, record_shelter_snapshot
from backend.services import apply_changes, audit, get_row, validate_team, serialize

router = APIRouter(prefix="/api", tags=["Response operations"])


@router.get("/shelters")
def shelters(district: str | None = None, db: Session = Depends(get_db)):
    query = select(Shelter)
    if district:
        query = query.where(Shelter.district == district)
    return [shelter_data(row) for row in db.scalars(query.order_by(Shelter.id))]


@router.get("/shelters/nearby")
def nearby(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), radius_km: float = Query(default=100, gt=0, le=500), db: Session = Depends(get_db)):
    return nearby_shelters(db, latitude, longitude, radius_km)


@router.post("/shelters", status_code=201)
def create_shelter(body: ShelterCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    validate_team(db, body.team_id, "shelter")
    row = Shelter(**body.model_dump())
    db.add(row)
    db.flush()
    record_shelter_snapshot(db, row, user)
    audit(db, user, "shelter.create", "shelter", row.id)
    db.commit()
    return shelter_data(row)


@router.put("/shelters/{shelter_id}")
def update_shelter(shelter_id: int, body: ShelterUpdate, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    row = get_row(db, Shelter, shelter_id, lock=True)
    if user.role != "admin":
        team = db.get(Team, user.team_id) if user.team_id else None
        if not team or team.team_type != "shelter" or row.team_id != team.id or body.model_fields_set - {"occupied", "facilities", "status"}:
            raise HTTPException(403, "Shelter teams may update occupancy and facilities of their assigned shelter")
    if "team_id" in body.model_fields_set:
        validate_team(db, body.team_id, "shelter")
    apply_changes(row, body, nullable=("team_id", "latitude", "longitude"))
    if row.occupied > row.capacity:
        raise HTTPException(422, "Occupancy cannot exceed shelter capacity")
    if (row.latitude is None) != (row.longitude is None):
        raise HTTPException(422, "Provide both latitude and longitude")
    row.updated_at = utcnow()
    record_shelter_snapshot(db, row, user)
    audit(db, user, "shelter.update", "shelter", row.id, {"occupied": row.occupied, "capacity": row.capacity})
    db.commit()
    return shelter_data(row)


@router.get("/shelters/{shelter_id}/history")
def shelter_history(shelter_id: int, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    row = get_row(db, Shelter, shelter_id)
    if user.role != "admin" and row.team_id != user.team_id:
        raise HTTPException(403, "Assigned shelter permission required")
    return {"updates": [serialize(item) for item in db.scalars(select(ShelterUpdateRecord).where(ShelterUpdateRecord.shelter_id == row.id).order_by(ShelterUpdateRecord.id))],
            "occupancy": [serialize(item) for item in db.scalars(select(ShelterOccupancy).where(ShelterOccupancy.shelter_id == row.id).order_by(ShelterOccupancy.id))]}
