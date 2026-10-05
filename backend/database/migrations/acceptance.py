"""Add acceptance tables/columns while preserving existing application records.

SQLite requires a transactional table copy to relax legacy NOT NULL constraints.
No table data is discarded, and unknown/custom incident columns abort that copy.
"""
from sqlalchemy import inspect, select, text
from sqlalchemy.schema import CreateTable, CreateIndex

from backend.database.connection import Base


ADDITIONS = {
    "report_analysis": {"history": "JSON NOT NULL DEFAULT '[]'"},
    "incident_reports": {"disaster_type_id": "INTEGER REFERENCES disaster_types(id)", "geocoding_consent": "BOOLEAN NOT NULL DEFAULT FALSE"},
    "assignments": {"accepted_at": "TIMESTAMP", "accepted_by": "INTEGER REFERENCES users(id)", "ended_at": "TIMESTAMP"},
    "chat_messages": {"session_id": "INTEGER REFERENCES chat_sessions(id)"},
    "news": {"verified": "BOOLEAN NOT NULL DEFAULT FALSE", "verified_by": "INTEGER REFERENCES users(id)", "verified_at": "TIMESTAMP", "verification_note": "TEXT NOT NULL DEFAULT ''"},
    "shelters": {"status": "VARCHAR(20) NOT NULL DEFAULT 'open'"},
    "relief_requests": {"assigned_team_id": "INTEGER REFERENCES teams(id)", "kind": "VARCHAR(30) NOT NULL DEFAULT 'supplies'"},
    "distributions": {"item": "VARCHAR(100) NOT NULL DEFAULT ''", "unit": "VARCHAR(50) NOT NULL DEFAULT 'units'"},
    "donation_pledges": {"proof_method": "VARCHAR(30)", "proof_reference": "VARCHAR(200)", "proof_note": "TEXT NOT NULL DEFAULT ''"},
}


def migrate_schema(engine):
    from backend.database import models  # Register complete metadata.
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table, additions in ADDITIONS.items():
            columns = {column["name"] for column in inspect(connection).get_columns(table)}
            for name, definition in additions.items():
                if name not in columns:
                    if engine.dialect.name == "postgresql":
                        definition = definition.replace("TIMESTAMP", "TIMESTAMP WITH TIME ZONE")
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))
        if engine.dialect.name == "postgresql":
            connection.execute(text("ALTER TABLE incident_reports ALTER COLUMN people_affected DROP NOT NULL"))
            connection.execute(text("ALTER TABLE incident_reports ALTER COLUMN location DROP NOT NULL"))
    if engine.dialect.name == "sqlite":
        columns = inspect(engine).get_columns("incident_reports")
        if any(not row["nullable"] for row in columns if row["name"] in ("people_affected", "location")):
            _relax_sqlite_incident(engine, models.Incident.__table__, columns)


def _relax_sqlite_incident(engine, table, columns):
    unknown = {row["name"] for row in columns} - set(table.columns.keys())
    if unknown:
        raise RuntimeError("Custom incident columns require a reviewed migration")
    ddl = str(CreateTable(table).compile(engine)).replace("CREATE TABLE incident_reports", "CREATE TABLE incident_reports_acceptance", 1)
    raw = engine.raw_connection()
    try:
        raw.rollback()
        cursor = raw.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(ddl)
        names = ", ".join('"' + row["name"] + '"' for row in columns)
        cursor.execute(f"INSERT INTO incident_reports_acceptance ({names}) SELECT {names} FROM incident_reports")
        before = cursor.execute("SELECT COUNT(*) FROM incident_reports").fetchone()[0]
        after = cursor.execute("SELECT COUNT(*) FROM incident_reports_acceptance").fetchone()[0]
        if before != after:
            raise RuntimeError("Incident migration count mismatch")
        cursor.execute("DROP TABLE incident_reports")
        cursor.execute("ALTER TABLE incident_reports_acceptance RENAME TO incident_reports")
        for index in table.indexes:
            cursor.execute(str(CreateIndex(index).compile(engine)))
        violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("Migration would violate foreign keys")
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.cursor().execute("PRAGMA foreign_keys=ON")
        raw.close()


def backfill_domain_records(db):
    """Materialize historical normalized records once; do not rewrite citizen facts."""
    from backend.database.models import (AlertMatch, ChatMessage, ChatSession, DisasterType, Distribution,
        Incident, Inventory, News, ReportAnalysis, RoleRecord, SeverityPrediction, Shelter,
        ShelterOccupancy, ShelterUpdateRecord, TeamMember, User, UserRole)
    from backend.services.auth_service import sync_account_membership
    from backend.services.shelter_service import record_shelter_snapshot
    for role_name in ("citizen", "response_team", "admin"):
        if not db.scalar(select(RoleRecord).where(RoleRecord.name == role_name)):
            db.add(RoleRecord(name=role_name))
    flood = db.scalar(select(DisasterType).where(DisasterType.name == "flood"))
    if not flood:
        flood = DisasterType(name="flood")
        db.add(flood)
    db.flush()
    for user in db.scalars(select(User)):
        sync_account_membership(db, user)
    for incident in db.scalars(select(Incident)):
        if not incident.disaster_type_id and incident.disaster_type == "flood":
            incident.disaster_type_id = flood.id
        if incident.analysis and not incident.analysis.history:
            incident.analysis.history = [{"created_at": incident.analysis.created_at.isoformat(), "result": incident.analysis.result}]
        if incident.analysis and not db.scalar(select(SeverityPrediction.id).where(SeverityPrediction.incident_id == incident.id)):
            result = incident.analysis.result
            db.add(SeverityPrediction(incident_id=incident.id, severity=result.get("severity", incident.severity), confidence=result.get("confidence"), result=result))
        if incident.analysis and not db.scalar(select(AlertMatch.id).where(AlertMatch.incident_id == incident.id)):
            match = incident.analysis.result.get("alert_match", {})
            if match:
                db.add(AlertMatch(incident_id=incident.id, status=match.get("status", "UNCERTAIN"), result=match))
    for shelter in db.scalars(select(Shelter)):
        if not db.scalar(select(ShelterUpdateRecord.id).where(ShelterUpdateRecord.shelter_id == shelter.id)):
            record_shelter_snapshot(db, shelter, None)
    for row in db.scalars(select(Distribution).where(Distribution.item == "")):
        stock = db.get(Inventory, row.inventory_id)
        if stock:
            row.item, row.unit = stock.item, stock.unit
    # Existing published content was already administrator approved. Record that
    # historical state rather than withdrawing it during an additive upgrade.
    for news in db.scalars(select(News).where(News.published.is_(True), News.verified.is_(False))):
        news.verified = True
        news.verification_note = "Previously published before separate verification was introduced"
    session_by_user = {}
    for message in db.scalars(select(ChatMessage).where(ChatMessage.session_id.is_(None))):
        if message.user_id not in session_by_user:
            session = ChatSession(user_id=message.user_id, title="Previous conversation")
            db.add(session)
            db.flush()
            session_by_user[message.user_id] = session.id
        message.session_id = session_by_user[message.user_id]
    db.flush()
