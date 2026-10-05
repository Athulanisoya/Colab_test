import base64
from uuid import uuid4

from backend.tests.conftest import auth


def test_health_and_public_information(client):
    assert client.get('/health').status_code == 200
    for path in ['/alerts', '/shelters', '/news', '/safety-tips', '/donations/campaigns']:
        response = client.get('/api' + path)
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)


def test_registration_cannot_choose_admin(client):
    body = {'name': 'Test citizen', 'email': f'{uuid4().hex}@example.org', 'password': 'StrongPass!2026', 'district': 'Ernakulam'}
    assert client.post('/api/auth/register', json={**body, 'role': 'admin'}).status_code == 422
    response = client.post('/api/auth/register', json=body)
    assert response.status_code in (200, 201), response.text
    assert response.json()['user']['role'] == 'citizen'
    assert client.post('/api/auth/register', json=body).status_code == 409


def test_authentication_and_permissions(client, headers):
    assert client.get('/api/users/me').status_code == 401
    assert client.post('/api/auth/login', json={'email': 'admin@resq.local', 'password': 'wrong'}).status_code == 401
    assert client.get('/api/admin/dashboard', headers=headers['citizen']).status_code == 403
    assert client.get('/api/admin/users', headers=headers['rescue']).status_code == 403
    assert client.get('/api/admin/dashboard', headers=headers['admin']).status_code == 200


def test_rotation_logout_revokes_access(client):
    session = client.post('/api/auth/login', json={'email': 'citizen@resq.local', 'password': 'ResqDemo!2026'}).json()
    fresh = client.post('/api/auth/refresh', json={'refresh_token': session['refresh_token']})
    assert fresh.status_code == 200, fresh.text
    assert client.post('/api/auth/refresh', json={'refresh_token': session['refresh_token']}).status_code == 401
    assert client.get('/api/users/me', headers=auth(session)).status_code == 401
    current = fresh.json()
    assert client.post('/api/auth/logout', headers=auth(current), json={'refresh_token': current['refresh_token']}).status_code in (200, 204)
    assert client.get('/api/users/me', headers=auth(current)).status_code == 401


def test_incident_owner_boundaries(client, headers, incident):
    account = client.post('/api/auth/register', json={'name': 'Other citizen', 'email': f'{uuid4().hex}@example.org', 'password': 'StrongPass!2026'}).json()
    assert client.get(f'/api/incidents/{incident["id"]}', headers=auth(account)).status_code in (403, 404)
    assert client.get(f'/api/incidents/{incident["id"]}', headers=headers['relief']).status_code in (403, 404)
    assert client.post(f'/api/incidents/{incident["id"]}/review', headers=headers['citizen'], json={'verified': True}).status_code == 403
    assert client.get('/api/incidents/my', headers=headers['citizen']).status_code == 200


def test_full_report_review_assignment_resolution(client, headers, incident):
    incident_id = incident['id']
    team_id = client.get('/api/users/me', headers=headers['rescue']).json()['team_id']
    assert client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': incident_id, 'team_id': team_id}).status_code == 409
    assert client.post(f'/api/incidents/{incident_id}/review', headers=headers['admin'], json={'verified': True, 'note': 'Confirmed by phone'}).status_code == 200
    assigned = client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': incident_id, 'team_id': team_id, 'note': 'Rescue children'})
    assert assigned.status_code in (200, 201), assigned.text
    assert client.post(f'/api/incidents/{incident_id}/status', headers=headers['rescue'], json={'status': 'resolved'}).status_code == 409
    assert client.post(f'/api/incidents/{incident_id}/status', headers=headers['rescue'], json={'status': 'en_route'}).status_code == 409
    accepted = client.post(f'/api/teams/assignments/{assigned.json()["assignment"]["id"]}/accept', headers=headers['rescue'])
    assert accepted.status_code == 200, accepted.text
    for status in ['en_route', 'in_progress', 'resolved']:
        response = client.post(f'/api/incidents/{incident_id}/status', headers=headers['rescue'], json={'status': status, 'note': 'Test status update'})
        assert response.status_code == 200, response.text
    assert client.post(f'/api/incidents/{incident_id}/status', headers=headers['rescue'], json={'status': 'closed'}).status_code == 403
    assert client.post(f'/api/incidents/{incident_id}/status', headers=headers['admin'], json={'status': 'closed', 'note': 'Citizen confirmed assistance'}).status_code == 200
    detail = client.get(f'/api/incidents/{incident_id}', headers=headers['citizen']).json()
    assert detail['status'] == 'closed'
    assert [event['status'] for event in detail['history']][-6:] == ['team_assigned', 'task_accepted', 'en_route', 'in_progress', 'resolved', 'closed']
    assert client.get('/api/notifications', headers=headers['citizen']).json()


def test_coordinates_and_quantities_validated(client, headers):
    body = {'message': 'Water is rising rapidly', 'location': 'Ranni', 'people_affected': 0, 'latitude': 100}
    assert client.post('/api/incidents', headers=headers['citizen'], json=body).status_code == 422
    assert client.post('/api/relief/request', headers=headers['citizen'], json={'location': 'Aluva', 'items': [{'item': 'Water', 'quantity': -1}]}).status_code == 422


def test_shelter_occupancy_and_team_scope(client, headers):
    shelters = client.get('/api/shelters').json()
    own_team = client.get('/api/users/me', headers=headers['shelter']).json()['team_id']
    own = next(row for row in shelters if row['team_id'] == own_team)
    other = next(row for row in shelters if row['team_id'] != own_team)
    assert client.put(f'/api/shelters/{own["id"]}', headers=headers['shelter'], json={'occupied': own['capacity'] + 1}).status_code in (400, 422)
    assert client.put(f'/api/shelters/{other["id"]}', headers=headers['shelter'], json={'occupied': 1}).status_code == 403
    assert client.put(f'/api/shelters/{own["id"]}', headers=headers['shelter'], json={'occupied': own['occupied']}).status_code == 200
    assert client.put(f'/api/shelters/{own["id"]}', headers=headers['citizen'], json={'occupied': 1}).status_code == 403


def test_relief_distribution_stock_and_requested_limits(client, headers):
    stock = client.post('/api/relief/inventory', headers=headers['admin'], json={'item': 'Test Water', 'quantity': 10, 'unit': 'bottles', 'location': 'Aluva'}).json()
    request = client.post('/api/relief/request', headers=headers['citizen'], json={'location': 'Aluva', 'items': [{'item': 'Test Water', 'quantity': 4}]}).json()
    body = {'request_id': request['id'], 'inventory_id': stock['id'], 'quantity': 11}
    assert client.post('/api/relief/distribution', headers=headers['admin'], json=body).status_code in (400, 409)
    assert client.post('/api/relief/distribution', headers=headers['citizen'], json={**body, 'quantity': 1}).status_code == 403
    response = client.post('/api/relief/distribution', headers=headers['admin'], json={**body, 'quantity': 4})
    assert response.status_code in (200, 201), response.text
    assert client.post('/api/relief/distribution', headers=headers['admin'], json={**body, 'quantity': 1}).status_code in (400, 409)
    updated = next(row for row in client.get('/api/relief/inventory', headers=headers['admin']).json() if row['id'] == stock['id'])
    assert updated['quantity'] == 6


def test_donations_are_pledges(client, headers):
    campaign_id = client.get('/api/donations/campaigns').json()[0]['id']
    response = client.post('/api/donations/pledges', headers=headers['citizen'], json={'campaign_id': campaign_id, 'kind': 'money', 'amount': 500})
    assert response.status_code in (200, 201), response.text
    assert response.json()['status'] == 'pledged'
    assert client.post('/api/donations/pledges', headers=headers['citizen'], json={'campaign_id': campaign_id, 'kind': 'money', 'amount': -1}).status_code == 422


def test_news_publication_is_admin_controlled(client, headers):
    body = {'title': 'Test verified update', 'content': 'A synthetic test update for the project demonstration.', 'published': False}
    assert client.post('/api/news', headers=headers['citizen'], json=body).status_code == 403
    created = client.post('/api/news', headers=headers['admin'], json=body)
    assert created.status_code in (200, 201), created.text
    news_id = created.json()['id']
    assert news_id not in [row['id'] for row in client.get('/api/news').json()]
    assert client.put(f'/api/news/{news_id}', headers=headers['admin'], json={'published': True}).status_code == 409
    assert client.post(f'/api/news/{news_id}/verify', headers=headers['admin'], json={'note': 'Reviewed against the coordination notice.'}).status_code == 200
    assert client.put(f'/api/news/{news_id}', headers=headers['admin'], json={'published': True}).status_code == 200
    assert news_id in [row['id'] for row in client.get('/api/news').json()]


def test_photo_validation_and_ownership(client, headers, incident):
    path = f'/api/incidents/{incident["id"]}/photo'
    assert client.post(path, headers=headers['citizen'], files={'file': ('bad.png', b'not an image', 'image/png')}).status_code in (400, 415, 422)
    assert client.get(path, headers=headers['relief']).status_code in (403, 404)


def test_notification_scope(client, headers):
    rows = client.get('/api/notifications', headers=headers['citizen']).json()
    assert rows
    assert client.post(f'/api/notifications/{rows[0]["id"]}/read', headers=headers['rescue']).status_code in (403, 404)
    assert client.post(f'/api/notifications/{rows[0]["id"]}/read', headers=headers['citizen']).status_code == 200


def test_admin_report_audit(client, headers):
    assert client.get('/api/admin/reports', headers=headers['admin']).status_code == 200
    assert client.get('/api/admin/audit-logs', headers=headers['admin']).json()
    assert client.get('/api/admin/audit-logs', headers=headers['citizen']).status_code == 403
