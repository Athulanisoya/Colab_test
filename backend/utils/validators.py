"""Database lookup, model serialization and validated patch application."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select


def serialize(row):
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()
        result[column.name] = value
    return result


def get_row(db, model, row_id, lock=False):
    # A previously loaded identity may be stale after waiting for another writer.
    # Refresh its state from the SELECT that acquired the row lock.
    row = db.scalar(select(model).where(model.id == row_id).with_for_update().execution_options(populate_existing=True)) if lock else db.get(model, row_id)
    if row is None:
        raise HTTPException(404, f"{model.__name__} not found")
    return row


def apply_changes(row, body, nullable=()):
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None and key not in nullable:
            raise HTTPException(422, f"{key} cannot be null")
        setattr(row, key, value)
