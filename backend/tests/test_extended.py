"""Security and operational tests without model generation or external services."""
import io
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from PIL import Image

from backend.tests.conftest import auth


def register_citizen(client):
    email = f'{uuid4().hex}@example.org'
    response = client.post('/api/auth/register', json={'name': 'Extended test citizen', 'email': email, 'password': 'StrongPass!2026'})
    assert response.status_code == 201, response.text
    return email, response.json()


def new_team(client, admin_headers, kind):
    response = client.post('/api/teams', headers=admin_headers, json={'name': f'Test {kind} {uuid4().hex[:8]}', 'team_type': kind, 'district': 'Alappuzha'})
    assert response.status_code == 201, response.text
    team = response.json()
    email = f'{uuid4().hex}@example.org'
    response = client.post('/api/admin/users', headers=admin_headers, json={'name': 'Test operator', 'email': email, 'password': 'StrongPass!2026', 'role': 'response_team', 'team_id': team['id']})
    assert response.status_code == 201, response.text
    session = client.post('/api/auth/login', json={'email': email, 'password': 'StrongPass!2026'}).json()
    return team, auth(session)


def test_investigation_review_and_rescue_reassignment(client, headers, incident):
    investigation, investigator = new_team(client, headers['admin'], 'investigation')
    rescue, rescuer = new_team(client, headers['admin'], 'rescue')
    report_id = incident['id']
    reviewed = client.post(f'/api/incidents/{report_id}/review', headers=headers['admin'], json={'verified': False, 'note': 'Location needs verification'})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()['verified'] is False
    assert client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': report_id, 'team_id': rescue['id']}).status_code == 409
    assert client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': report_id, 'team_id': investigation['id']}).status_code == 200
    body = {'verified': True, 'people_affected': 4, 'required_items': ['Rescue'], 'findings': 'Synthetic field check confirmed the family needs assistance.'}
    assert client.post(f'/api/investigation/{report_id}/report', headers=rescuer, json=body).status_code == 403
    response = client.post(f'/api/investigation/{report_id}/report', headers=investigator, json=body)
    assert response.status_code == 201, response.text
    # Field findings cannot independently verify or dispatch a rescue team.
    assert client.get(f'/api/incidents/{report_id}', headers=headers['admin']).json()['verified'] is False
    reviewed = client.post(f'/api/incidents/{report_id}/review', headers=headers['admin'], json={'verified': True, 'note': 'Admin accepted field findings'})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()['status'] == 'under_review'
    assigned = client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': report_id, 'team_id': rescue['id']})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()['assignment']['team_id'] == rescue['id']
    assert client.get(f'/api/incidents/{report_id}', headers=investigator).status_code == 403
    team = next(row for row in client.get('/api/teams', headers=headers['admin']).json() if row['id'] == investigation['id'])
    assert team['available'] is True


def test_password_reset_reuse_and_session_revocation(client, headers):
    from urllib.parse import parse_qs
    def delivered_token(email):
        messages = client.get('/api/admin/recovery-mail', headers=headers['admin']).json()
        message = next(row for row in messages if row['recipient'] == email)
        return parse_qs(message['reset_url'].split('?', 1)[1])['token'][0]
    email, original = register_citizen(client)
    first = client.post('/api/auth/forgot-password', json={'email': email})
    assert 'demo_token' not in first.json()
    old_token = delivered_token(email)
    reset = client.post('/api/auth/forgot-password', json={'email': email})
    assert reset.status_code == 200, reset.text
    assert 'demo_token' not in reset.json()
    token = delivered_token(email)
    body = {'token': token, 'password': 'ChangedPass!2026'}
    assert client.post('/api/auth/reset-password', json=body).status_code == 200
    assert client.post('/api/auth/reset-password', json=body).status_code == 400
    assert client.post('/api/auth/reset-password', json={'token': old_token, 'password': 'ReplayedPass!2026'}).status_code == 400
    assert client.get('/api/users/me', headers=auth(original)).status_code == 401
    assert client.post('/api/auth/refresh', json={'refresh_token': original['refresh_token']}).status_code == 401
    assert client.post('/api/auth/login', json={'email': email, 'password': 'StrongPass!2026'}).status_code == 401
    assert client.post('/api/auth/login', json={'email': email, 'password': 'ChangedPass!2026'}).status_code == 200


def test_deactivation_revokes_tokens_and_prevents_login(client, headers):
    email, original = register_citizen(client)
    response = client.put(f'/api/admin/users/{original["user"]["id"]}', headers=headers['admin'], json={'active': False})
    assert response.status_code == 200, response.text
    assert response.json()['active'] is False
    assert client.get('/api/users/me', headers=auth(original)).status_code == 401
    assert client.post('/api/auth/refresh', json={'refresh_token': original['refresh_token']}).status_code == 401
    assert client.post('/api/auth/login', json={'email': email, 'password': 'StrongPass!2026'}).status_code == 401


@pytest.mark.parametrize('same_request', [False, True])
def test_concurrent_distributions_respect_stock_and_remaining_request(client, headers, same_request):
    item = f'Concurrent Water {uuid4().hex[:8]}'
    stock = client.post('/api/relief/inventory', headers=headers['admin'], json={'item': item, 'quantity': 10, 'unit': 'bottles', 'location': 'Test hub'}).json()
    quantity = 3 if same_request else 7
    requested = 5 if same_request else 7
    requests = []
    for _ in range(1 if same_request else 2):
        response = client.post('/api/relief/request', headers=headers['citizen'], json={'location': 'Test location', 'items': [{'item': item, 'quantity': requested}]})
        assert response.status_code == 201, response.text
        requests.append(response.json())
    request_ids = [requests[0]['id'], requests[0]['id'] if same_request else requests[1]['id']]
    def send(request_id):
        return client.post('/api/relief/distribution', headers=headers['admin'], json={'request_id': request_id, 'inventory_id': stock['id'], 'quantity': quantity})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, request_ids))
    assert sorted(response.status_code for response in results) == [201, 409], [response.text for response in results]
    inventory = next(row for row in client.get('/api/relief/inventory', headers=headers['admin']).json() if row['id'] == stock['id'])
    assert inventory['quantity'] == 10 - quantity


def test_team_cannot_change_type_or_manage_other_team(client, headers):
    own = client.get('/api/users/me', headers=headers['shelter']).json()['team_id']
    other = client.get('/api/users/me', headers=headers['rescue']).json()['team_id']
    assert client.put(f'/api/teams/{own}', headers=headers['shelter'], json={'team_type': 'rescue'}).status_code == 403
    assert client.put(f'/api/teams/{other}', headers=headers['shelter'], json={'available': True}).status_code == 403


def test_valid_photo_reencoded_and_access_scoped(client, headers, incident):
    stream = io.BytesIO()
    Image.new('RGB', (10, 10), 'blue').save(stream, format='PNG')
    path = f'/api/incidents/{incident["id"]}/photo'
    response = client.post(path, headers=headers['citizen'], files={'file': ('tiny.png', stream.getvalue(), 'image/png')})
    assert response.status_code == 200, response.text
    assert response.json()['photo_url'] == path
    image = client.get(path, headers=headers['citizen'])
    assert image.status_code == 200
    assert image.headers['content-type'] == 'image/jpeg'
    assert Image.open(io.BytesIO(image.content)).format == 'JPEG'
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers['relief']).status_code == 403


def test_report_timestamps_have_explicit_utc_offset(client, headers, incident):
    response = client.get(f'/api/incidents/{incident["id"]}', headers=headers['citizen'])
    assert response.json()['created_at'].endswith('+00:00')
    assert response.json()['history'][0]['created_at'].endswith('+00:00')


def test_ai_severity_helper_requires_authentication_and_returns_local_result(client, headers):
    body = {'message': 'Two children are trapped inside the flooded house'}
    assert client.post('/api/ai/severity', json=body).status_code == 401
    response = client.post('/api/ai/severity', headers=headers['citizen'], json=body)
    assert response.status_code == 200, response.text
    assert response.json()['severity'] == 'HIGH'


def test_chat_context_is_scoped_and_compact(client, headers, incident, monkeypatch):
    _, other = register_citizen(client)
    other_report = client.post('/api/incidents', headers=auth(other), json={'message': 'A private report from a different citizen', 'location': 'Private test location'}).json()
    captured = {}
    async def answer(message, context):
        captured.update(context)
        return {'answer': 'Your status is available in My reports.', 'sources': [], 'provider': 'test', 'model': 'test', 'status': 'completed'}
    monkeypatch.setattr('backend.ai.chatbot.answer_question', answer)
    response = client.post('/api/chatbot/chat', headers=headers['citizen'], json={'message': 'What is my report status?'})
    assert response.status_code == 200, response.text
    assert other_report['id'] not in [row['id'] for row in captured['incidents']]
    assert incident['id'] in [row['id'] for row in captured['incidents']]
    assert len(captured['alerts']) <= 10
    assert len(captured['shelters']) <= 10
    for row in captured['incidents']:
        assert not {'message', 'history', 'analysis'} & row.keys()
        assert len(row['summary']) <= 250


def test_logout_rejects_an_unrelated_session_token(client):
    email, first = register_citizen(client)
    second = client.post('/api/auth/login', json={'email': email, 'password': 'StrongPass!2026'}).json()
    response = client.post('/api/auth/logout', headers=auth(first), json={'refresh_token': second['refresh_token']})
    assert response.status_code == 401
    assert client.get('/api/users/me', headers=auth(first)).status_code == 200
    assert client.post('/api/auth/logout', headers=auth(first), json={'refresh_token': first['refresh_token']}).status_code == 200
    assert client.get('/api/users/me', headers=auth(first)).status_code == 401
    assert client.get('/api/users/me', headers=auth(second)).status_code == 200
