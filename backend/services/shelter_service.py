"""Shelter availability projection and geographic distance search."""
import math

from sqlalchemy import select

from backend.models.shelter import Shelter, ShelterOccupancy, ShelterUpdateRecord
from backend.utils.validators import serialize


def shelter_data(row):
    available = row.capacity - row.occupied if row.status == "open" else 0
    return {**serialize(row), "available_capacity": available}


def record_shelter_snapshot(db, row, user):
    actor_id = user.id if user else None
    db.add(ShelterUpdateRecord(shelter_id=row.id, actor_id=actor_id,
        snapshot={"name": row.name, "location": row.location, "district": row.district,
                  "capacity": row.capacity, "occupied": row.occupied, "facilities": row.facilities,
                  "status": row.status, "team_id": row.team_id, "latitude": row.latitude, "longitude": row.longitude}))
    db.add(ShelterOccupancy(shelter_id=row.id, actor_id=actor_id, occupied=row.occupied, capacity=row.capacity))


def nearby_shelters(db, latitude, longitude, radius_km=100):
    rows = []
    for shelter in db.scalars(select(Shelter).where(Shelter.latitude.is_not(None), Shelter.longitude.is_not(None), Shelter.status == "open", Shelter.occupied < Shelter.capacity)):
        lat1, lat2 = math.radians(latitude), math.radians(shelter.latitude)
        a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(shelter.longitude - longitude) / 2) ** 2
        distance = 6371 * 2 * math.asin(math.sqrt(min(1, a)))
        if distance <= radius_km:
            rows.append({**shelter_data(shelter), "distance_km": round(distance, 2)})
    return sorted(rows, key=lambda row: row["distance_km"])
