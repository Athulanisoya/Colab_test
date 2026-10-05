"""Client acceptance regressions for clarification, handoff and dispatch."""
from uuid import uuid4

from backend.tests.test_extended import new_team, register_citizen
from backend.tests.conftest import auth


def advance(client, headers, incident, states):
    assigned = client.get(f'/api/incidents/{incident["id"]}', headers=headers).json()
    if assigned['status'] == 'team_assigned':
        response = client.post(f'/api/teams/assignments/{assigned["assignment"]["id"]}/accept', headers=headers)
        assert response.status_code == 200, response.text
    for state in states:
        response = client.post(f'/api/incidents/{incident["id"]}/status', headers=headers, json={'status': state, 'note': 'Client acceptance workflow update'})
        assert response.status_code == 200, response.text


def test_missing_facts_and_real_clarification_preserve_original(client, headers):
    message = 'Several people need help. Please help us find a safe place.'
    created = client.post('/api/incidents', headers=headers['citizen'], json={'message': message})
    assert created.status_code == 201, created.text
    incident = created.json()
    assert incident['people_affected'] is None  # Unknown is not a fabricated count of one.
    assert incident['clarification']['status'] == 'open'
    _, other = register_citizen(client)
    path = f'/api/incidents/{incident["id"]}/clarification-reply'
    assert client.post(path, headers=auth(other), json={'answer': 'Unrelated person'}).status_code == 403
    reply = client.post(path, headers=headers['citizen'], json={
        'answer': 'We are twelve people at Chengannur town.', 'location': 'Chengannur',
        'district': 'Alappuzha', 'people_affected': 12,
    })
    assert reply.status_code == 200, reply.text
    result = reply.json()
    assert result['message'] == message
    assert result['people_affected'] == 12 and result['location'] == 'Chengannur'
    assert result['analysis']['clarification_answers'][-1]['answer'].startswith('We are twelve')
    assert result['analysis']['analysis_status'] != 'pending'


def test_rescue_handoff_relief_team_distribution_and_final_closure(client, headers, incident):
    rescue, rescuer = new_team(client, headers['admin'], 'rescue')
    relief, operator = new_team(client, headers['admin'], 'relief')
    ident = incident['id']
    assert client.post(f'/api/incidents/{ident}/review', headers=headers['admin'], json={'verified': True}).status_code == 200
    assert client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': ident, 'team_id': rescue['id']}).status_code == 200
    advance(client, rescuer, incident, ['en_route', 'in_progress'])
    item = 'Handoff water ' + uuid4().hex[:8]
    stock = client.post('/api/relief/inventory', headers=headers['admin'], json={'item': item, 'unit': 'bottles', 'quantity': 10, 'location': 'Depot'}).json()
    path = f'/api/incidents/{ident}/handoff'
    body = {'team_id': relief['id'], 'note': 'Rescue complete; household needs relief supplies.',
            'items': [{'item': item, 'unit': 'bottles', 'quantity': 3}]}
    assert client.post(path, headers=rescuer, json=body).status_code == 403
    handoff = client.post(path, headers=headers['admin'], json=body)
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()['assignment']['team_id'] == relief['id']
    assert client.get(f'/api/incidents/{ident}', headers=rescuer).status_code == 403
    requests = client.get('/api/relief/requests', headers=operator).json()
    request = next(row for row in requests if row['incident_id'] == ident)
    advance(client, operator, incident, ['en_route', 'in_progress'])
    assert client.post(f'/api/incidents/{ident}/status', headers=operator, json={'status': 'resolved'}).status_code == 409
    response = client.post('/api/relief/distribution', headers=operator, json={'request_id': request['id'], 'inventory_id': stock['id'], 'quantity': 3})
    assert response.status_code == 201, response.text
    assert response.json()['unit'] == 'bottles' and response.json()['request_status'] == 'fulfilled'
    advance(client, operator, incident, ['resolved'])
    assert client.post(f'/api/incidents/{ident}/status', headers=headers['admin'], json={'status': 'closed', 'note': 'Citizen confirms all assistance received.'}).status_code == 200
    assert client.get(f'/api/incidents/{ident}', headers=headers['citizen']).json()['status'] == 'closed'


def test_independent_request_assignment_and_mixed_unit_protection(client, headers):
    team, operator = new_team(client, headers['admin'], 'relief')
    item = 'Mixed water ' + uuid4().hex[:8]
    stocks = {}
    for unit in ('litres', 'bottles'):
        stocks[unit] = client.post('/api/relief/inventory', headers=headers['admin'], json={'item': item, 'unit': unit, 'quantity': 20, 'location': 'Depot'}).json()
    body = {'location': 'Independent household', 'items': [{'item': item, 'quantity': 5}]}
    assert client.post('/api/relief/request', headers=headers['citizen'], json=body).status_code == 422
    body['items'][0]['unit'] = 'bottles'
    request = client.post('/api/relief/request', headers=headers['citizen'], json=body).json()
    assert request['incident_id'] is None
    assigned = client.post(f'/api/relief/requests/{request["id"]}/assign', headers=headers['admin'], json={'team_id': team['id'], 'note': 'Send the relief team to this household.'})
    assert assigned.status_code == 200, assigned.text
    assert request['id'] in [row['id'] for row in client.get('/api/relief/requests', headers=operator).json()]
    payload = {'request_id': request['id'], 'inventory_id': stocks['litres']['id'], 'quantity': 5}
    assert client.post('/api/relief/distribution', headers=operator, json=payload).status_code == 422
    payload['inventory_id'] = stocks['bottles']['id']
    delivered = client.post('/api/relief/distribution', headers=operator, json=payload)
    assert delivered.status_code == 201, delivered.text
    assert client.put(f'/api/relief/inventory/{payload["inventory_id"]}', headers=headers['admin'], json={'unit': 'litres'}).status_code == 409
    assert delivered.json()['unit'] == 'bottles'


def test_independent_rescue_support_dispatch(client, headers):
    team, operator = new_team(client, headers['admin'], 'rescue')
    request = client.post('/api/relief/request', headers=headers['citizen'], json={'kind': 'rescue_support', 'items': [], 'location': 'Isolated household', 'note': 'We need evacuation assistance.'})
    assert request.status_code == 201, request.text
    ident = request.json()['id']
    response = client.post(f'/api/relief/requests/{ident}/assign', headers=headers['admin'], json={'team_id': team['id'], 'note': 'Coordinate rescue support for the household.'})
    assert response.status_code == 200, response.text
    assert client.post(f'/api/relief/requests/{ident}/complete', headers=headers['citizen'], json={'note': 'Cannot complete my own dispatch.'}).status_code == 403
    complete = client.post(f'/api/relief/requests/{ident}/complete', headers=operator, json={'note': 'Household moved to the safe assembly point.'})
    assert complete.status_code == 200, complete.text
    assert complete.json()['status'] == 'fulfilled'


def test_monitoring_records_an_actual_no_report_decision(client, headers):
    point = 'Quiet area ' + uuid4().hex[:8]
    alert = client.post('/api/alerts', headers=headers['admin'], json={'title': 'Area requires monitoring', 'message': 'Synthetic alert used only for client acceptance.', 'location': point, 'district': 'Alappuzha'}).json()
    assert client.get('/api/admin/monitoring', headers=headers['citizen']).status_code == 403
    row = next(row for row in client.get('/api/admin/monitoring', headers=headers['admin']).json() if row['alert_id'] == alert['id'])
    assert row['status'] == 'no_report' and row['report_count'] == 0
    response = client.post(f'/api/admin/monitoring/{alert["id"]}', headers=headers['admin'], json={'action': 'investigate', 'note': 'Seek field verification; silence does not establish safety.'})
    assert response.status_code == 200, response.text
    row = next(row for row in client.get('/api/admin/monitoring', headers=headers['admin']).json() if row['alert_id'] == alert['id'])
    assert row['decision']['action'] == 'investigate' and row['monitoring_note']


def test_chat_session_reuses_only_owners_history_and_relief_records(client, headers, monkeypatch):
    captured = []
    async def answer(message, context):
        captured.append(context)
        return {'answer': 'Read the current request status in your records.', 'sources': [], 'status': 'completed'}
    monkeypatch.setattr('backend.ai.chatbot.answer_question', answer)
    request = client.post('/api/relief/request', headers=headers['citizen'], json={'location': 'Chat status household', 'items': [{'item': 'Blankets', 'quantity': 2, 'unit': 'pieces'}]}).json()
    first = client.post('/api/chatbot/chat', headers=headers['citizen'], json={'message': f'What is request #{request["id"]} status?'}).json()
    assert request['id'] in [row['id'] for row in captured[-1]['relief_requests']]
    second = client.post('/api/chatbot/chat', headers=headers['citizen'], json={'message': 'What happens next?', 'session_id': first['session_id']})
    assert second.status_code == 200 and captured[-1]['conversation'][0]['role'] == 'user'
    _, other = register_citizen(client)
    assert client.post('/api/chatbot/chat', headers=auth(other), json={'message': 'Show me the private history', 'session_id': first['session_id']}).status_code == 403
    assert client.get(f'/api/chatbot/history?session_id={first["session_id"]}', headers=auth(other)).status_code == 403


def test_duplicate_metadata_is_visible_only_to_admin(client, headers, incident):
    from backend.database.connection import SessionLocal
    from backend.models.incident import Incident
    with SessionLocal() as db:
        row = db.get(Incident, incident['id'])
        row.analysis.result = {**row.analysis.result, 'duplicate_candidates': [{'id': 999, 'score': .9}], 'duplicates': [{'id': 999}]}
        db.commit()
    citizen = client.get(f'/api/incidents/{incident["id"]}', headers=headers['citizen']).json()
    admin = client.get(f'/api/incidents/{incident["id"]}', headers=headers['admin']).json()
    assert 'duplicate_candidates' not in citizen['analysis'] and 'duplicates' not in citizen['analysis']
    assert admin['analysis']['duplicate_candidates'][0]['id'] == 999
