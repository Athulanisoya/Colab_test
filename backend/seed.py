"""Clearly synthetic demo data. Never seeded when DEMO_MODE is false."""
from datetime import timedelta

from sqlalchemy import select

from backend.database.models import Alert, Assignment, AuditLog, Campaign, Incident, Inventory, News, Notification, ReliefRequest, ReportAnalysis, SafetyTip, Shelter, StatusHistory, Team, User, utcnow
from backend.utils.security import hash_password


def seed_demo(db):
    if db.scalar(select(User.id).limit(1)):
        return
    teams = {}
    for kind, name, district in [
        ("rescue", "Chengannur Rescue Unit", "Alappuzha"),
        ("investigation", "Ranni Investigation Unit", "Pathanamthitta"),
        ("relief", "Aluva Relief Unit", "Ernakulam"),
        ("shelter", "Chengannur Shelter Desk", "Alappuzha"),
    ]:
        team = Team(name=name, team_type=kind, district=district, available=True)
        db.add(team)
        db.flush()
        teams[kind] = team
    second_shelter_team = Team(name="Aluva Shelter Desk", team_type="shelter", district="Ernakulam", available=True)
    db.add(second_shelter_team)
    db.flush()
    password_hash = hash_password("ResqDemo!2026")
    citizen = User(name="Anu Nair", email="citizen@resq.local", password_hash=password_hash, district="Alappuzha", role="citizen")
    admin = User(name="District Coordinator", email="admin@resq.local", password_hash=password_hash, district="Alappuzha", role="admin")
    db.add_all([citizen, admin])
    for kind in ("rescue", "investigation", "relief", "shelter"):
        db.add(User(name=teams[kind].name, email=f"{kind}@resq.local", password_hash=password_hash, district=teams[kind].district, role="response_team", team_id=teams[kind].id))
    db.flush()
    db.add_all([
        Alert(title="Demo · Chengannur flood watch", message="Synthetic demonstration alert. This is not a live warning. The project scenario assumes rising water near Chengannur.", district="Alappuzha", location="Chengannur", severity="high", expires_at=utcnow() + timedelta(days=7)),
        Alert(title="Demo · Aluva preparedness update", message="Synthetic demonstration alert. Check the project shelter directory and keep your report location precise.", district="Ernakulam", location="Aluva", severity="moderate", expires_at=utcnow() + timedelta(days=7)),
        Shelter(name="Demo · Chengannur Community Hall", location="Chengannur", district="Alappuzha", capacity=180, occupied=72, facilities=["Drinking water", "Toilets", "Family area", "Accessibility support"], latitude=9.318, longitude=76.615, team_id=teams["shelter"].id),
        Shelter(name="Demo · Aluva School Shelter", location="Aluva", district="Ernakulam", capacity=120, occupied=38, facilities=["Meals", "Toilets", "First aid desk"], latitude=10.107, longitude=76.351, team_id=second_shelter_team.id),
        Shelter(name="Demo · Ranni Relief Camp", location="Ranni", district="Pathanamthitta", capacity=90, occupied=24, facilities=["Drinking water", "Meals", "Family area"], latitude=9.384, longitude=76.801, team_id=None),
        Inventory(item="Water", quantity=800, unit="bottles", location="Aluva distribution hub"),
        Inventory(item="Food", quantity=400, unit="kits", location="Chengannur distribution hub"),
        Inventory(item="Clothing", quantity=180, unit="sets", location="Aluva distribution hub"),
        Inventory(item="Medicine", quantity=75, unit="sealed kits", location="Chengannur first aid desk"),
        Campaign(title="Demo · Kerala flood relief", description="Synthetic campaign for demonstrating money and supply pledges. No money is collected through this application.", target_amount=250000),
        News(title="Welcome to the ResQ Kerala demonstration", content="Every seeded alert, incident, team, shelter and campaign is synthetic. Use this local prototype to explore reporting, human review, team assignment and relief coordination.", source="Project demonstration", published=True),
        News(title="How to submit a useful report", content="Give a precise location and district, explain what happened, estimate the people affected and choose the assistance required. Administrators verify reports before operational assignment.", source="ResQ Kerala project guide", published=True),
        SafetyTip(title="Use current official guidance", content="Check current instructions from Kerala State Disaster Management Authority and local authorities. Project demo alerts and shelter records are not live official information.", category="information", source="https://sdma.kerala.gov.in/"),
        SafetyTip(title="Make your report clear", content="Include your location, number of people affected and assistance needed. Keep sensitive personal details out of public messages. Your incident report is visible only to you, administrators and the assigned response team.", category="reporting", source="ResQ Kerala project guide"),
        SafetyTip(title="Keep contact information available", content="Use the emergency contacts provided by official authorities for urgent help. Submitting a prototype report does not contact or dispatch real emergency services.", category="preparedness", source="https://sdma.kerala.gov.in/"),
    ])
    specs = [
        ("RQ-DEMO-001", "Demo: Water has entered the ground floor in Chengannur. Four people need food and drinking water.", "Chengannur", "Alappuzha", 4, ["Food", "Water"], "submitted", "moderate", None),
        ("RQ-DEMO-002", "Demo: A family reported rising water near Ranni. Please verify the location and check whether assistance is needed.", "Ranni", "Pathanamthitta", 3, ["Investigation"], "team_assigned", "moderate", "investigation"),
        ("RQ-DEMO-003", "Demo: The family at Aluva needs food and water after reaching higher ground.", "Aluva", "Ernakulam", 5, ["Food", "Water"], "team_assigned", "moderate", "relief"),
        ("RQ-DEMO-004", "Demo: Two children and their grandparents were rescued from a flooded house in Chengannur.", "Chengannur", "Alappuzha", 4, ["Rescue"], "closed", "high", "rescue"),
    ]
    for reference, message, location, district, people, assistance, status, severity, kind in specs:
        report = Incident(reference=reference, message=message, location=location, district=district, people_affected=people, help_required=assistance, user_id=citizen.id, status=status, severity=severity, verified=True if kind != "investigation" else False)
        db.add(report)
        db.flush()
        report.analysis = ReportAnalysis(result={"analysis_status": "demo_fixture", "provider": "synthetic_demo", "model": "demo", "summary": "Synthetic fixture for demonstration; no model inference was performed for this seeded report.", "severity": severity.upper(), "confidence": None, "english_translation": message, "extracted_location": location, "required_assistance": assistance, "alert_match": {"status": "MATCH" if district != "Pathanamthitta" else "NO_MATCH"}, "duplicate_ids": [], "investigation_required": kind == "investigation", "recommended_action": "Administrator review required before operational action."})
        db.add(StatusHistory(incident_id=report.id, status="submitted", note="Synthetic demo report", actor_id=citizen.id))
        if kind:
            assignment = Assignment(incident_id=report.id, team_id=teams[kind].id, assigned_by=admin.id, note="Synthetic demonstration assignment")
            db.add(assignment)
            if status != "closed":
                teams[kind].available = False
            statuses = ["under_review", "team_assigned"] if status != "closed" else ["under_review", "team_assigned", "en_route", "in_progress", "resolved", "closed"]
            for value in statuses:
                db.add(StatusHistory(incident_id=report.id, status=value, note="Synthetic demonstration history", actor_id=admin.id))
        if kind == "relief":
            db.add(ReliefRequest(user_id=citizen.id, incident_id=report.id, items=[{"item": "Food", "quantity": 5}, {"item": "Water", "quantity": 10}], location=location, note="Synthetic demonstration request"))
    db.add(Notification(user_id=citizen.id, title="Welcome to ResQ Kerala", message="This is a local demonstration with synthetic records. Track your reports and explore the response workflow."))
    db.add(AuditLog(actor_id=admin.id, action="demo.seed", entity_type="system", detail={"synthetic": True}))
    db.commit()
