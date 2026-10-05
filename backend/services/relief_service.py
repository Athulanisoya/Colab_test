"""Relief accounting and atomic stock allocation."""
from fastapi import HTTPException
from sqlalchemy import func, select, text, update

from backend.models.incident import Incident
from backend.models.inventory import Distribution, Inventory, ReliefRequest
from backend.models.team import Team
from backend.utils.permissions import active_assignment
from backend.utils.validators import get_row, serialize
from .notification_service import audit, notify


def locked_relief_request(db, request_id):
    """Keep linked-case operations in incident, request, team lock order."""
    snapshot = get_row(db, ReliefRequest, request_id)
    if snapshot.incident_id:
        get_row(db, Incident, snapshot.incident_id, lock=True)
    return get_row(db, ReliefRequest, request_id, lock=True)


def relief_data(db, row):
    data = serialize(row)
    data["distributions"] = [serialize(record) for record in db.scalars(select(Distribution).where(Distribution.request_id == row.id))]
    team = db.get(Team, row.assigned_team_id) if row.assigned_team_id else None
    data["assignment"] = {"team_id": team.id, "team_name": team.name, "team_type": team.team_type} if team else None
    return data


def normalize_requested_items(db, items):
    """Resolve a missing unit only if the stock catalog is unambiguous."""
    result = []
    for item in items:
        value = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        if value.get("inventory_id"):
            stock = get_row(db, Inventory, value["inventory_id"])
            if stock.item.casefold() != value["item"].casefold():
                raise HTTPException(422, "Selected stock does not match the requested item")
            if value.get("unit") and value["unit"].casefold() != stock.unit.casefold():
                raise HTTPException(422, "Requested unit does not match the selected stock")
            value["unit"] = stock.unit
        elif not value.get("unit"):
            units = list(db.scalars(select(Inventory.unit).where(func.lower(Inventory.item) == value["item"].lower()).distinct()))
            normalized = {unit.casefold(): unit for unit in units}
            if len(normalized) > 1:
                raise HTTPException(422, "Specify a unit: this item has stock in different units")
            value["unit"] = next(iter(normalized.values()), "units")
        result.append(value)
    keys = [(item["item"].casefold(), item["unit"].casefold()) for item in result]
    if len(keys) != len(set(keys)):
        raise HTTPException(422, "Combine duplicate items with the same unit")
    return result


def distribute_relief(db, user, body):
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    request = locked_relief_request(db, body.request_id)
    from .team_service import lock_teams, team_has_active_incident
    locked = lock_teams(db, (request.assigned_team_id, user.team_id))
    stock = get_row(db, Inventory, body.inventory_id, lock=True)
    if user.role != "admin":
        team = locked.get(user.team_id)
        if not team or team.team_type != "relief":
            raise HTTPException(403, "An assigned relief team is required")
        incident = db.get(Incident, request.incident_id) if request.incident_id else None
        assignment = active_assignment(incident) if incident else None
        if request.assigned_team_id != team.id and not (assignment and assignment.team_id == team.id):
            raise HTTPException(403, "This relief request is not assigned to your team")
    if request.kind != "supplies":
        raise HTTPException(422, "Rescue support is completed through team response, not stock allocation")
    if request.status in ("fulfilled", "cancelled"):
        raise HTTPException(409, "Request is already fulfilled")
    request.items = normalize_requested_items(db, request.items)
    requested = next((item["quantity"] for item in request.items if item["item"].casefold() == stock.item.casefold()
                      and item["unit"].casefold() == stock.unit.casefold()
                      and (not item.get("inventory_id") or item["inventory_id"] == stock.id)), None)
    if requested is None:
        raise HTTPException(422, "Selected item and unit were not requested")
    delivered = db.scalar(select(func.coalesce(func.sum(Distribution.quantity), 0)).where(Distribution.request_id == request.id,
                           func.lower(Distribution.item) == stock.item.lower(), func.lower(Distribution.unit) == stock.unit.lower()))
    if body.quantity > requested - delivered:
        raise HTTPException(409, "Quantity exceeds the undelivered request amount")
    changed = db.execute(update(Inventory).where(Inventory.id == stock.id, Inventory.quantity >= body.quantity).values(quantity=Inventory.quantity - body.quantity))
    if changed.rowcount != 1:
        raise HTTPException(409, "Insufficient inventory stock")
    row = Distribution(**body.model_dump(), actor_id=user.id, item=stock.item, unit=stock.unit)
    db.add(row)
    db.flush()
    totals = {(name, unit): quantity for name, unit, quantity in db.execute(
        select(func.lower(Distribution.item), func.lower(Distribution.unit), func.sum(Distribution.quantity))
        .where(Distribution.request_id == request.id).group_by(func.lower(Distribution.item), func.lower(Distribution.unit)))}
    request.status = "fulfilled" if all(totals.get((item["item"].lower(), item["unit"].lower()), 0) >= item["quantity"] for item in request.items) else "partially_fulfilled"
    if request.status == "fulfilled" and request.assigned_team_id:
        db.flush()
        team = locked[request.assigned_team_id]
        team.available = not team_has_active_incident(db, team.id)
    audit(db, user, "relief.distribute", "distribution", row.id, {"inventory_id": stock.id, "quantity": body.quantity, "request_id": request.id})
    notify(db, request.user_id, "Relief distribution recorded", f"{body.quantity} {stock.unit} of {stock.item} allocated to your request.", request.incident_id)
    db.commit()
    return {**serialize(row), "request_status": request.status, "remaining_stock": stock.quantity}
