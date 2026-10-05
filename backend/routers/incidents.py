import asyncio
import io
import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from backend.config import settings
from backend.database.connection import SessionLocal, get_db
from backend.database.models import Alert, Incident, InvestigationReport, ReportAnalysis, StatusHistory, Team, User, utcnow
from backend.models.incident import Assignment, AlertMatch, DisasterType, SeverityPrediction
from backend.models.inventory import ReliefRequest
from backend.models.user import AuditLog
from backend.schemas import IncidentCreate, InvestigationCreate, Review, StatusUpdate
from backend.utils.jwt import get_current_user
from backend.utils.permissions import require_admin
from backend.services import active_assignment, audit, get_row, incident_query, notify, require_assigned_team, require_incident_access, serialize, serialize_incident, status_change
from backend.services.team_service import lock_teams, team_has_active_incident
from backend.schemas.incident_schema import ClarificationReply, MonitoringDecision
from backend.schemas.relief_schema import IncidentHandoff
from backend.services.relief_service import normalize_requested_items
from backend.services.alert_service import report_matches_alert

router = APIRouter(prefix="/api", tags=["Incidents"])
logger = logging.getLogger(__name__)


async def process_incident(incident_id: int):
    with SessionLocal() as db:
        incident = db.get(Incident, incident_id)
        if not incident:
            return
        payload = {key: getattr(incident, key) for key in ("message", "location", "district", "people_affected", "help_required", "geocoding_consent")}
        answers = incident.analysis.result.get("clarification_answers", []) if incident.analysis else []
        payload["clarification_answers"] = answers
        if answers:
            payload["message"] += "\nCitizen follow-up facts: " + "\n".join(str(answer["answer"]) for answer in answers[-3:])
        payload["alerts"] = [serialize(row) for row in db.scalars(select(Alert).where(Alert.active.is_(True), (Alert.expires_at.is_(None)) | (Alert.expires_at > utcnow())))]
        payload["duplicates"] = [{"id": row.id, "message": row.message, "location": row.location, "district": row.district,
                                  "english_translation": row.analysis.result.get("english_translation", "") if row.analysis else ""}
                                 for row in db.scalars(select(Incident).where(Incident.id != incident.id).order_by(Incident.id.desc()).limit(100))]
        payload["teams"] = [{**serialize(row), "active_assignment_count": int(team_has_active_incident(db, row.id))}
                            for row in db.scalars(select(Team))]
    try:
        from backend.ai.agent import analyze_report
        result = await asyncio.wait_for(analyze_report(**payload), timeout=settings.ai_timeout_seconds + 15)
    except Exception as error:
        # Never log the original message or a provider request containing personal data.
        logger.warning("Incident AI processing unavailable: %s", type(error).__name__)
        result = {"analysis_status": "unavailable", "provider": "ollama", "model": settings.ollama_model,
                  "summary": "AI analysis is unavailable. The original report is preserved for administrator review.",
                  "severity": "pending", "confidence": None, "investigation_required": True,
                  "recommended_action": "Review the original report and verify urgency manually."}
    matching = result.get("alert_match") or {}
    matched_ids = matching.get("matched_alert_ids", matching.get("alert_ids", [])) or []
    if matching:
        # Preserve the geography actually compared, rather than the alert's
        # potentially edited geography when processing finishes.
        result["alert_match"] = {**matching, "matched_alert_snapshots": [
            {key: alert[key] for key in ("id", "location", "district")}
            for alert in payload["alerts"] if alert["id"] in matched_ids]}
    with SessionLocal() as db:
        incident = db.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
        if not incident:
            return
        prior = incident.analysis.result if incident.analysis else {}
        if prior.get("clarification_answers"):
            result["clarification_answers"] = prior["clarification_answers"]
            if result.get("clarification", {}).get("status") == "resolved":
                result["clarification"] = {**result["clarification"], "status": "answered", **prior["clarification_answers"][-1]}
        extracted_facts = {"location": result.get("extracted_location"), "district": result.get("district"), "people_affected": result.get("people_affected")}
        for key, value in extracted_facts.items():
            if getattr(incident, key) in (None, "") and value not in (None, ""):
                setattr(incident, key, value)
        if not incident.help_required and result.get("required_assistance"):
            incident.help_required = result["required_assistance"]
        if not incident.location or not incident.district:
            question = "Please confirm your nearest landmark and district so a coordinator can locate you."
            missing = [key for key in ("location", "district") if not getattr(incident, key)]
            missing.extend(key for key in result.get("clarification", {}).get("missing_fields", []) if key not in missing)
            result["clarification"] = {"status": "open", "question": question, "missing_fields": missing}
            result["clarification_question"] = question
            result["investigation_required"] = True
        if incident.analysis:
            incident.analysis.history = [*(incident.analysis.history or []), {"recorded_at": utcnow().isoformat(), "result": result}]
            incident.analysis.result = result
            incident.analysis.created_at = utcnow()
        else:
            incident.analysis = ReportAnalysis(result=result, history=[{"recorded_at": utcnow().isoformat(), "result": result}])
        severity = str(result.get("severity", "pending")).lower()
        incident.severity = severity if severity in ("low", "moderate", "high") else "pending"
        db.add(SeverityPrediction(incident_id=incident.id, severity=incident.severity, confidence=result.get("confidence"),
                                 result={key: result.get(key) for key in ("severity", "confidence", "baseline_severity", "baseline_confidence", "danger_flag", "severity_source")}))
        matching = result.get("alert_match", {})
        ids = matching.get("alert_ids", matching.get("matched_alert_ids", []))
        for alert_id in ids or [None]:
            db.add(AlertMatch(incident_id=incident.id, alert_id=alert_id, status=matching.get("status", "UNCERTAIN"), result=matching))
        notify(db, incident.user_id, "Report analysis updated", f"{incident.reference} is ready for human review.", incident.id)
        db.commit()


@router.post("/incidents", status_code=201)
async def create_incident(body: IncidentCreate, background: BackgroundTasks, wait_for_analysis: bool = True, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "citizen":
        raise HTTPException(403, "Citizen account required to submit a report")
    incident = Incident(**body.model_dump(), user_id=user.id, reference="RQ-" + utcnow().strftime("%y%m%d") + "-" + secrets.token_hex(3).upper())
    flood = db.scalar(select(DisasterType).where(DisasterType.name == "flood"))
    if flood:
        incident.disaster_type_id = flood.id
    db.add(incident)
    db.flush()
    incident.analysis = ReportAnalysis(result={"analysis_status": "pending", "provider": "ollama", "model": settings.ollama_model, "summary": "Report saved. AI analysis is queued; administrator verification is required."})
    db.add(StatusHistory(incident_id=incident.id, status="submitted", note="Citizen report received", actor_id=user.id))
    audit(db, user, "incident.create", "incident", incident.id)
    for admin_id in db.scalars(select(User.id).where(User.role == "admin", User.active.is_(True))):
        notify(db, admin_id, "New citizen report", f"{incident.reference} in {incident.location}, {incident.district}", incident.id)
    db.commit()
    db.refresh(incident)
    if wait_for_analysis:
        await process_incident(incident.id)
        db.expire_all()
    else:
        background.add_task(process_incident, incident.id)
    return serialize_incident(incident, user)


@router.get("/incidents/my")
def my_incidents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [serialize_incident(row, user) for row in db.scalars(select(Incident).where(Incident.user_id == user.id).order_by(Incident.id.desc()))]


@router.get("/incidents")
def incidents(status: str | None = None, district: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = incident_query(user)
    if status:
        query = query.where(Incident.status == status)
    if district:
        query = query.where(Incident.district == district)
    return [serialize_incident(row, user) for row in db.scalars(query.order_by(Incident.id.desc())).unique()]


@router.get("/incidents/{incident_id}")
def detail(incident_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_row(db, Incident, incident_id)
    require_incident_access(user, row)
    return serialize_incident(row, user)


@router.get("/incidents/{incident_id}/status")
def history(incident_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_row(db, Incident, incident_id)
    require_incident_access(user, row)
    return {"id": row.id, "status": row.status, "history": [serialize(item) for item in row.history]}


@router.post("/incidents/{incident_id}/clarification-reply")
async def clarify(incident_id: int, body: ClarificationReply, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    row = get_row(db, Incident, incident_id, lock=True)
    if row.user_id != user.id:
        raise HTTPException(403, "Only the report owner can answer clarification")
    if row.status not in ("submitted", "under_review"):
        raise HTTPException(409, "Clarification must be completed before operational assignment")
    prior = dict(row.analysis.result) if row.analysis else {}
    if prior.get("analysis_status") == "pending":
        raise HTTPException(409, "Wait for the current analysis before replying")
    clarification = prior.get("clarification", {})
    if clarification.get("status") != "open" and not prior.get("clarification_question"):
        raise HTTPException(409, "This report has no open clarification")
    facts = body.model_dump(exclude_unset=True, exclude={"answer"})
    for key, value in facts.items():
        if key != "landmark" and value is not None:
            setattr(row, key, value)
    reply = {"answer": body.answer, "answered_at": utcnow().isoformat(), **facts}
    answers = [*prior.get("clarification_answers", []), reply]
    # Preserve original text. The answer is a separate, attributable report fact.
    prior.update({"analysis_status": "pending", "clarification": {**clarification, "status": "answered", **reply}, "clarification_answers": answers})
    if row.analysis:
        row.analysis.result = prior
    else:
        row.analysis = ReportAnalysis(result=prior)
    audit(db, user, "incident.clarification", "incident", row.id, {"answer": body.answer, "facts": facts})
    db.add(StatusHistory(incident_id=row.id, status=row.status, actor_id=user.id, note="Citizen answered location clarification"))
    db.commit()
    await process_incident(row.id)
    db.expire_all()
    return serialize_incident(row, user)


@router.post("/incidents/{incident_id}/handoff")
def handoff(incident_id: int, body: IncidentHandoff, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    row = get_row(db, Incident, incident_id, lock=True)
    current = active_assignment(row)
    if not current or current.team.team_type != "rescue" or row.status not in ("in_progress", "resolved") or row.verified is not True:
        raise HTTPException(409, "A verified rescue case in progress or resolved is required")
    pending = list(db.scalars(select(ReliefRequest).where(ReliefRequest.incident_id == row.id,
                                                       ReliefRequest.status.notin_(["fulfilled", "cancelled"])).order_by(ReliefRequest.id)
                              .with_for_update().execution_options(populate_existing=True)))
    get_row(db, Team, body.team_id)
    released_ids = {current.team_id, *(request.assigned_team_id for request in pending if request.assigned_team_id)} - {body.team_id}
    teams = lock_teams(db, (body.team_id, *released_ids))
    team = teams[body.team_id]
    if team.team_type != "relief":
        raise HTTPException(422, "Select a relief team for this handoff")
    if not team.available or team_has_active_incident(db, team.id):
        raise HTTPException(409, "Selected relief team is unavailable")
    values = normalize_requested_items(db, body.items)
    if not pending and not values:
        raise HTTPException(422, "Specify required supplies or create a linked relief request")
    if values:
        pending.append(ReliefRequest(user_id=row.user_id, incident_id=row.id, location=row.location or "Location awaiting confirmation",
                                    kind="supplies", items=values, note=body.note, status="assigned"))
    if any(request.kind != "supplies" for request in pending):
        raise HTTPException(409, "Complete rescue support requests before handing off to relief")
    current.active = False
    current.ended_at = utcnow()
    for request in pending:
        request.assigned_team_id = team.id
        request.status = "assigned" if request.status == "pending" else request.status
        db.add(request)
    assignment = Assignment(incident_id=row.id, team_id=team.id, assigned_by=user.id, note=body.note)
    db.add(assignment)
    team.available = False
    status_change(db, row, "team_assigned", user, body.note)
    # Evaluate availability after all moved work and the replacement assignment
    # are visible. Keep a former team busy when it still has other work.
    db.flush()
    for team_id in released_ids:
        teams[team_id].available = not team_has_active_incident(db, team_id)
    audit(db, user, "incident.relief_handoff", "incident", row.id, {"from_team_id": current.team_id, "team_id": team.id})
    for member in db.scalars(select(User).where(User.team_id == team.id, User.active.is_(True))):
        notify(db, member.id, "Rescue to relief handoff", f"{row.reference}: {body.note}", row.id)
    db.commit()
    db.refresh(row)
    return serialize_incident(row, user)


@router.get("/admin/monitoring")
def monitoring(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    alerts = db.scalars(select(Alert).where(Alert.active.is_(True), (Alert.expires_at.is_(None)) | (Alert.expires_at > utcnow())))
    current_reports = list(db.scalars(select(Incident).where(Incident.status != "closed").options(selectinload(Incident.analysis))))
    result = []
    for alert in alerts:
        reports = [report for report in current_reports if report_matches_alert(report, alert)]
        decision = db.scalar(select(AuditLog).where(AuditLog.action == "monitoring.decision", AuditLog.entity_type == "alert",
                                                   AuditLog.entity_id == alert.id).order_by(AuditLog.id.desc()).limit(1))
        result.append({**serialize(alert), "alert_id": alert.id, "report_count": len(reports),
                       "last_report_at": max((serialize(report)["created_at"] for report in reports), default=None),
                       "status": "reports_received" if reports else "no_report", "monitoring_note": decision.detail.get("note") if decision else None,
                       "decision": decision.detail if decision else None,
                       "recommended_action": "Review reported conditions" if reports else "Monitor and seek field verification; silence is not evidence of safety"})
    return result


@router.post("/admin/monitoring/{alert_id}")
def monitoring_decision(alert_id: int, body: MonitoringDecision, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    alert = get_row(db, Alert, alert_id)
    audit(db, user, "monitoring.decision", "alert", alert.id, body.model_dump())
    for member in db.scalars(select(User).join(Team, User.team_id == Team.id).where(
        User.active.is_(True), Team.team_type == "investigation", Team.district == alert.district)):
        notify(db, member.id, "Alert area monitoring", f"{alert.location}: {body.note}")
    db.commit()
    return {"alert_id": alert.id, **body.model_dump(), "recorded_at": utcnow().isoformat()}


@router.post("/incidents/{incident_id}/analyze", status_code=202)
def analyze(incident_id: int, background: BackgroundTasks, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    row = get_row(db, Incident, incident_id, lock=True)
    if row.analysis and row.analysis.result.get("analysis_status") == "pending":
        raise HTTPException(409, "Analysis is already queued")
    result = {**(row.analysis.result if row.analysis else {}), "analysis_status": "pending", "summary": "AI reanalysis queued", "provider": "ollama", "model": settings.ollama_model}
    if row.analysis:
        row.analysis.result = result
    else:
        row.analysis = ReportAnalysis(result=result)
    audit(db, user, "incident.analyze", "incident", row.id)
    db.commit()
    background.add_task(process_incident, row.id)
    return {"message": "Analysis queued", "incident_id": row.id}


@router.post("/incidents/{incident_id}/review")
def review(incident_id: int, body: Review, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    row = get_row(db, Incident, incident_id, lock=True)
    previous_assignment = active_assignment(row)
    is_investigation_followup = previous_assignment and previous_assignment.team.team_type == "investigation" and db.scalar(select(InvestigationReport.id).where(InvestigationReport.incident_id == row.id))
    if row.status not in ("submitted", "under_review") and not (is_investigation_followup and row.status != "closed"):
        raise HTTPException(409, "Review is allowed before team assignment")
    if is_investigation_followup:
        team = get_row(db, Team, previous_assignment.team_id, lock=True)
        previous_assignment.active = False
        team.available = not team_has_active_incident(db, team.id, exclude_incident_id=row.id)
    row.verified = body.verified
    status_change(db, row, "under_review", user, body.note or ("Administrator verified report" if body.verified else "Further investigation required"))
    audit(db, user, "incident.review", "incident", row.id, {"verified": body.verified})
    db.commit()
    db.refresh(row)
    return serialize_incident(row, user)


@router.post("/incidents/{incident_id}/status")
def update_status(incident_id: int, body: StatusUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    row = get_row(db, Incident, incident_id, lock=True)
    require_assigned_team(user, row)
    transitions = {"task_accepted": "en_route", "en_route": "in_progress", "in_progress": "resolved", "resolved": "closed"}
    if transitions.get(row.status) != body.status:
        raise HTTPException(409, f"Cannot change {row.status} to {body.status}")
    if body.status == "closed" and user.role != "admin":
        raise HTTPException(403, "Only an administrator can close a case")
    if body.status in ("resolved", "closed") and db.scalar(select(ReliefRequest.id).where(
        ReliefRequest.incident_id == row.id, ReliefRequest.status.notin_(["fulfilled", "cancelled"])).limit(1)):
        raise HTTPException(409, "Complete or hand off the linked assistance requests before resolving the case")
    status_change(db, row, body.status, user, body.note)
    if body.status == "resolved":
        assignment = active_assignment(row)
        if assignment:
            # Keep the assignment active for case-history access; availability is an operator decision.
            team = get_row(db, Team, assignment.team_id, lock=True)
            team.available = not team_has_active_incident(db, team.id, exclude_incident_id=row.id)
    db.commit()
    db.refresh(row)
    return serialize_incident(row, user)


@router.post("/investigation/{incident_id}/report", status_code=201)
def investigation_report(incident_id: int, body: InvestigationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    incident = get_row(db, Incident, incident_id, lock=True)
    require_assigned_team(user, incident)
    assignment = active_assignment(incident)
    if not assignment or assignment.team.team_type != "investigation":
        raise HTTPException(403, "An assigned investigation team is required")
    if incident.status not in ("team_assigned", "task_accepted", "en_route", "in_progress"):
        raise HTTPException(409, "The incident is not open for investigation")
    row = InvestigationReport(**body.model_dump(), incident_id=incident.id, team_id=assignment.team_id)
    db.add(row)
    audit(db, user, "investigation.report", "incident", incident.id, {"verified": body.verified})
    for admin_id in db.scalars(select(User.id).where(User.role == "admin", User.active.is_(True))):
        notify(db, admin_id, "Investigation findings submitted", f"Review {incident.reference}: {body.findings[:180]}", incident.id)
    db.commit()
    return serialize(row)


@router.get("/investigation/{incident_id}/reports")
def investigations(incident_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    incident = get_row(db, Incident, incident_id)
    require_incident_access(user, incident)
    return [serialize(row) for row in db.scalars(select(InvestigationReport).where(InvestigationReport.incident_id == incident_id).order_by(InvestigationReport.id.desc()))]


@router.post("/incidents/{incident_id}/photo")
async def upload_photo(incident_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_row(db, Incident, incident_id)
    if row.user_id != user.id:
        raise HTTPException(403, "Only the report owner can upload a photo")
    if row.status in ("resolved", "closed"):
        raise HTTPException(409, "Completed-case evidence cannot be replaced")
    if file.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(422, "Upload a JPEG or PNG image")
    data = await file.read(5 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Photos must be 5 MB or smaller")
    try:
        with Image.open(io.BytesIO(data)) as uploaded:
            if uploaded.format not in ("JPEG", "PNG") or uploaded.width * uploaded.height > 25000000:
                raise ValueError("Unsupported image")
            uploaded.verify()
        with Image.open(io.BytesIO(data)) as uploaded:
            normalized = uploaded.convert("RGB")
            normalized.thumbnail((2048, 2048))
            output = io.BytesIO()
            normalized.save(output, format="JPEG", quality=85)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "The file is not a valid supported image")
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Stable ID-only filenames avoid user-controlled paths. Re-encoding strips EXIF/GPS metadata.
    target = upload_dir / f"incident-{row.id}.jpg"
    target.write_bytes(output.getvalue())
    row.photo_url = f"/api/incidents/{row.id}/photo"
    audit(db, user, "incident.photo", "incident", row.id)
    db.commit()
    return {"photo_url": row.photo_url}


@router.get("/incidents/{incident_id}/photo")
def read_photo(incident_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_row(db, Incident, incident_id)
    require_incident_access(user, row)
    target = Path(settings.upload_dir) / f"incident-{row.id}.jpg"
    if not row.photo_url or not target.is_file():
        raise HTTPException(404, "No photo attached")
    return FileResponse(target, media_type="image/jpeg", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
