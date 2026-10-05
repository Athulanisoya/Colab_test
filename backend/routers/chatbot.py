import asyncio
import re

from fastapi import APIRouter, Depends
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import Alert, ChatMessage, Incident, SafetyTip, Shelter, User, utcnow
from backend.models.user import ChatSession
from backend.models.inventory import ReliefRequest
from backend.services.relief_service import relief_data
from backend.services.shelter_service import shelter_data
from backend.config import settings
from backend.schemas import AIInput, ChatInput
from backend.utils.jwt import get_current_user
from backend.services.alert_service import active_alert_query
from backend.services import active_assignment, get_row, incident_query, serialize

router = APIRouter(prefix="/api")


def _incident_context(row) -> dict:
    """Project only authorized operational fields; omit staff notes and identity."""
    assignment = active_assignment(row)
    # Incidents have a creation timestamp and immutable status events, not an
    # updated_at column. Expose the latest recorded status-event time explicitly.
    created_at = serialize(row)["created_at"]
    status_updated_at = serialize(row.history[-1])["created_at"] if row.history else created_at
    return {
        "id": row.id, "reference": row.reference, "location": row.location,
        "district": row.district, "status": row.status, "severity": row.severity,
        "help_required": row.help_required,
        "summary": str(row.analysis.result.get("summary", ""))[:250] if row.analysis else "",
        "updated_at": status_updated_at,
        "assignment": {
            "active": True, "team_name": assignment.team.name,
            "team_type": assignment.team.team_type,
            "created_at": serialize(assignment)["created_at"],
        } if assignment else None,
    }


@router.post("/chatbot/chat", tags=["Community information"])
async def chat(body: ChatInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.session_id:
        session = get_row(db, ChatSession, body.session_id)
        if session.user_id != user.id:
            from fastapi import HTTPException
            raise HTTPException(403, "This conversation belongs to another user")
    else:
        session = ChatSession(user_id=user.id, title=body.message[:120])
        db.add(session)
        db.flush()
    prior = list(db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id, ChatMessage.user_id == user.id)
                           .order_by(ChatMessage.id.desc()).limit(6)))
    conversation = []
    for record in reversed(prior):
        conversation.extend([{"role": "user", "content": record.message}, {"role": "assistant", "content": record.answer}])
    # Prioritize explicit references and matching place names before bounded context.
    lookup = body.message + " " + " ".join(turn["content"] for turn in conversation[-2:])
    mentioned_ids = [int(value) for value in re.findall(r"(?:report|request|case|#)\s*#?(\d+)", lookup, flags=re.I)]
    mentioned_references = [value.upper() for value in re.findall(r"\bRQ-[\w-]+\b", lookup, flags=re.I)]
    words = [word for word in re.findall(r"[\w\u0D00-\u0D7F]{3,}", body.message) if word.casefold() not in {"what", "where", "status", "report", "shelter", "request", "please"}]
    shelter_match = or_(*[or_(Shelter.name.ilike(f"%{word}%"), Shelter.location.ilike(f"%{word}%"), Shelter.district.ilike(f"%{word}%")) for word in words]) if words else Shelter.district == user.district
    shelter_query = select(Shelter).order_by(case((shelter_match, 0), else_=1), case((Shelter.district == user.district, 0), else_=1), Shelter.id.desc()).limit(10)
    scoped_incidents = incident_query(user).order_by(case((or_(Incident.id.in_(mentioned_ids), Incident.reference.in_(mentioned_references)), 0), else_=1), Incident.id.desc()).limit(10)
    relief_query = select(ReliefRequest)
    if user.role == "citizen":
        relief_query = relief_query.where(ReliefRequest.user_id == user.id)
    elif user.role == "response_team":
        own_ids = incident_query(user).with_only_columns(Incident.id)
        relief_query = relief_query.where(or_(ReliefRequest.assigned_team_id == user.team_id, ReliefRequest.incident_id.in_(own_ids)))
    context = {
        "role": user.role,
        "snapshot_at": utcnow().isoformat(),
        "user_name": user.name,
        "district": user.district,
        "alerts": [{"id": row.id, "title": row.title, "message": row.message[:300], "location": row.location, "district": row.district, "severity": row.severity,
                    "created_at": serialize(row)["created_at"], "expires_at": serialize(row)["expires_at"]}
                   for row in db.scalars(active_alert_query().order_by(Alert.id.desc()).limit(10))],
        "shelters": [{"id": row.id, "name": row.name, "location": row.location, "district": row.district, "available_capacity": shelter_data(row)["available_capacity"], "status": row.status, "facilities": row.facilities,
                      "updated_at": serialize(row)["updated_at"]}
                     for row in db.scalars(shelter_query)],
        "safety_tips": [{"id": row.id, "title": row.title, "content": row.content[:300], "source": row.source}
                        for row in db.scalars(select(SafetyTip).limit(10))],
        "incidents": [_incident_context(row)
                      for row in db.scalars(scoped_incidents).unique()],
        "relief_requests": [{key: value for key, value in relief_data(db, row).items() if key in ("id", "kind", "incident_id", "location", "status", "items", "assignment", "created_at")}
                            for row in db.scalars(relief_query.order_by(case((ReliefRequest.id.in_(mentioned_ids), 0), else_=1), ReliefRequest.id.desc()).limit(10))],
        "conversation": conversation,
    }
    try:
        from backend.ai.chatbot import answer_question
        result = await asyncio.wait_for(answer_question(body.message, context), timeout=settings.ai_timeout_seconds + 15)
    except Exception:
        result = {"answer": "The local AI service is unavailable. Check your reports, active alerts and shelter directory directly in the app. For immediate danger, contact local emergency services.", "sources": [], "provider": "ollama", "model": settings.ollama_model, "status": "unavailable"}
    db.add(ChatMessage(user_id=user.id, session_id=session.id, message=body.message, answer=result["answer"], sources=result.get("sources", [])))
    session.updated_at = utcnow()
    db.commit()
    return {**result, "session_id": session.id}


@router.get("/chatbot/history", tags=["Community information"])
def chat_history(session_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(ChatMessage).where(ChatMessage.user_id == user.id)
    if session_id:
        session = get_row(db, ChatSession, session_id)
        if session.user_id != user.id:
            from fastapi import HTTPException
            raise HTTPException(403, "This conversation belongs to another user")
        query = query.where(ChatMessage.session_id == session_id)
    return [serialize(row) for row in db.scalars(query.order_by(ChatMessage.id.desc()).limit(30))]


@router.get("/chatbot/sessions", tags=["Community information"])
def chat_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc()).limit(30))]


@router.post("/ai/severity", tags=["AI helpers"])
async def severity(body: AIInput, user: User = Depends(get_current_user)):
    from backend.ai.severity_model import classify_report
    return await classify_report(body.message)


@router.post("/ai/translate", tags=["AI helpers"])
async def translate(body: AIInput, user: User = Depends(get_current_user)):
    from backend.ai.translator import translate_report
    return await translate_report(**body.model_dump())


@router.post("/ai/location", tags=["AI helpers"])
async def location(body: AIInput, user: User = Depends(get_current_user)):
    from backend.ai.location_extractor import extract_location
    return await extract_location(**body.model_dump())


@router.post("/ai/summary", tags=["AI helpers"])
async def summary(body: AIInput, user: User = Depends(get_current_user)):
    from backend.ai.summarizer import summarize_report
    return await summarize_report(**body.model_dump())
