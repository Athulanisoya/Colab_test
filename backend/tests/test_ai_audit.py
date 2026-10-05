"""Audit regressions for provenance and authorized application context; no GPU."""
import asyncio
import json
from datetime import datetime
from uuid import uuid4

import pytest

from backend.ai import chatbot
from backend.ai.rag import retrieve_safety
from backend.tests.conftest import auth


@pytest.mark.parametrize("question", [
    "Can I drive through a flooded road?",
    "What should I do during a flood?",
    "വെള്ളത്തിലൂടെ വാഹനം ഓടിക്കാമോ?",
])
def test_safety_answer_without_citation_uses_grounded_fallback(monkeypatch, question):
    async def fake_run(*args, **kwargs):
        return json.dumps({"answer": "UNCITED_GENERATED_ADVICE", "source_ids": []}), []
    monkeypatch.setattr(chatbot, "_run_agent", fake_run)
    result = asyncio.run(chatbot.answer_question(question))
    assert result["status"] == "unavailable"
    assert "UNCITED_GENERATED_ADVICE" not in result["answer"]
    assert "Official safety guidance retrieved locally" in result["answer"]
    assert result["sources"]


@pytest.mark.parametrize("question,answer", [
    ("How do I report a flood?", "Select Report an incident and then track it in My reports."),
    ("Walk me through reporting an incident.", "Select Report an incident and then track it in My reports."),
    ("What is my report status?", "Your report is under review. Check My reports for updates."),
    ("Which team is assigned to my incident?", "Your supplied application snapshot shows Test rescue."),
    ("Which nearby shelter has available space?", "The supplied shelter has 20 spaces; availability can change."),
])
def test_portal_and_status_answers_may_have_no_safety_citation(monkeypatch, question, answer):
    async def fake_run(*args, **kwargs):
        return json.dumps({"answer": answer, "source_ids": []}), []
    monkeypatch.setattr(chatbot, "_run_agent", fake_run)
    context={'incidents':[{'id':1,'reference':'RQ-OWN','status':'under_review','assignment':{'active':True,'team_name':'Test rescue','team_type':'rescue'}}],
             'shelters':[{'name':'Test shelter','available_capacity':20}]}
    result = asyncio.run(chatbot.answer_question(question,context))
    assert result["status"] == "completed"
    if 'assigned' in question:
        assert 'Test rescue' in result['answer']
    elif 'status' in question:
        assert 'under_review' in result['answer']
    elif 'shelter' in question:
        assert '20' in result['answer'] and 'change' in result['answer']
    else:
        assert 'Report an incident' in result['answer'] and 'My reports' in result['answer']
    assert result["sources"] == []


def test_safety_advice_added_to_portal_answer_still_requires_provenance(monkeypatch):
    async def fake_run(*args, **kwargs):
        return '{"answer":"Check My reports. Do not drive through floodwater.","source_ids":[]}', []
    monkeypatch.setattr(chatbot, "_run_agent", fake_run)
    result = asyncio.run(chatbot.answer_question("What is my report status?"))
    assert result["status"] == "completed"
    assert result["model_response_status"] == "rejected"
    assert result["answer_provider"] == "authorized_database_snapshot"
    assert "No matching report" in result["answer"]
    assert result["answer"] != "Check My reports. Do not drive through floodwater."


def test_safety_answer_with_retrieved_citation_remains_completed(monkeypatch):
    question = "Can I drive through a flooded road?"
    source = retrieve_safety(question)[0]["id"]
    async def fake_run(*args, **kwargs):
        return json.dumps({"answer": "Avoid driving through floodwater.", "source_ids": [source]}), []
    monkeypatch.setattr(chatbot, "_run_agent", fake_run)
    result = asyncio.run(chatbot.answer_question(question))
    assert result["status"] == "completed"
    assert [item["id"] for item in result["sources"]] == [source]


def test_unknown_citation_remains_rejected_for_portal_answer(monkeypatch):
    async def fake_run(*args, **kwargs):
        return '{"answer":"Check My reports.","source_ids":["unknown-source"]}', []
    monkeypatch.setattr(chatbot, "_run_agent", fake_run)
    result = asyncio.run(chatbot.answer_question("How do I report an incident?"))
    assert result["status"] == "completed"
    assert result["model_response_status"] == "rejected"
    assert result["answer_provider"] == "authorized_database_snapshot"
    assert "Report an incident" in result["answer"]
    assert not any(item["id"] == "unknown-source" for item in result["sources"])


def test_actual_chat_context_has_authorized_assignment_and_utc_snapshot(client, headers, monkeypatch):
    def citizen():
        response = client.post('/api/auth/register', json={
            'name': 'Audit citizen', 'email': f'{uuid4().hex}@example.org', 'password': 'StrongPass!2026',
        })
        assert response.status_code == 201, response.text
        return response.json()
    owner, other = citizen(), citizen()
    def report(session, location):
        response = client.post('/api/incidents', headers=auth(session), json={
            'message': 'Synthetic audit report requesting assistance.', 'location': location,
            'district': 'Alappuzha', 'people_affected': 2,
        })
        assert response.status_code == 201, response.text
        return response.json()
    own_report = report(owner, 'Chengannur')
    private_report = report(other, 'PRIVATE_OTHER_LOCATION')
    team = client.post('/api/teams', headers=headers['admin'], json={
        'name': f'Audit rescue {uuid4().hex[:8]}', 'team_type': 'rescue', 'district': 'Alappuzha',
    })
    assert team.status_code == 201, team.text
    team = team.json()
    assert client.post(f'/api/incidents/{own_report["id"]}/review', headers=headers['admin'], json={'verified': True}).status_code == 200
    assigned = client.post('/api/teams/assign', headers=headers['admin'], json={
        'incident_id': own_report['id'], 'team_id': team['id'], 'note': 'PRIVATE_STAFF_NOTE',
    })
    assert assigned.status_code == 200, assigned.text
    captured = {}
    async def fake_answer(message, context):
        captured.update(chatbot._compact_context(context))
        return {'answer': 'Check My reports.', 'sources': [], 'status': 'completed'}
    monkeypatch.setattr(chatbot, 'answer_question', fake_answer)
    response = client.post('/api/chatbot/chat', headers=auth(owner), json={'message': 'Which team is assigned to my report?'})
    assert response.status_code == 200, response.text
    assert [row['id'] for row in captured['incidents']] == [own_report['id']]
    record = captured['incidents'][0]
    assert record['assignment']['team_name'] == team['name']
    assert record['assignment']['team_type'] == 'rescue'
    for value in (captured['snapshot_at'], record['updated_at'], record['assignment']['created_at']):
        assert datetime.fromisoformat(value).utcoffset().total_seconds() == 0
    assert captured['shelters']
    assert all(row['updated_at'] for row in captured['shelters'])
    assert captured['alerts']
    assert all('expires_at' in row and row['created_at'] for row in captured['alerts'])
    encoded = json.dumps(captured)
    assert 'PRIVATE_STAFF_NOTE' not in encoded
    assert 'PRIVATE_OTHER_LOCATION' not in encoded
    assert str(private_report['reference']) not in encoded
    assert not {'assigned_by', 'user_name', 'user_id', 'note', 'summary'} & record['assignment'].keys()


def test_retrieval_miss_cannot_approve_uncited_guidance(monkeypatch):
    async def fake_run(*args, **kwargs):
        return '{"answer":"UNSUPPORTED_GUIDANCE","source_ids":[]}', []
    monkeypatch.setattr(chatbot, "_run_agent", fake_run)
    monkeypatch.setattr(chatbot, "retrieve_safety", lambda message: [])
    result = asyncio.run(chatbot.answer_question("What should I do during inundation?"))
    assert result["status"] == "unavailable"
    assert "UNSUPPORTED_GUIDANCE" not in result["answer"]


def test_retrieval_miss_allows_clear_no_verified_information(monkeypatch):
    async def fake_run(*args, **kwargs):
        return '{"answer":"I do not have verified information about that topic.","source_ids":[]}', []
    monkeypatch.setattr(chatbot, "_run_agent", fake_run)
    monkeypatch.setattr(chatbot, "retrieve_safety", lambda message: [])
    result = asyncio.run(chatbot.answer_question("Tell me about an unrelated topic."))
    assert result["status"] == "completed"
    assert result["sources"] == []
