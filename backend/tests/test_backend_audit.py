"""Regression evidence for independently audited workflow and reporting defects."""
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest

from backend.tests.conftest import auth


def provision_team(client, admin, kind="rescue", available=True):
    response = client.post('/api/teams', headers=admin, json={
        'name': f'Audit {kind} {uuid4().hex[:8]}', 'team_type': kind,
        'district': 'Alappuzha', 'available': available,
    })
    assert response.status_code == 201, response.text
    team = response.json()
    email = f'{uuid4().hex}@audit.example.org'
    response = client.post('/api/admin/users', headers=admin, json={
        'name': 'Audit response operator', 'email': email, 'password': 'AuditPass!2026',
        'role': 'response_team', 'team_id': team['id'],
    })
    assert response.status_code == 201, response.text
    session = client.post('/api/auth/login', json={'email': email, 'password': 'AuditPass!2026'})
    assert session.status_code == 200, session.text
    return team, auth(session.json())


def reviewed_report(client, headers, verified=True):
    response = client.post('/api/incidents', headers=headers['citizen'], json={
        'message': 'Private audit household needs water and rescue assistance.',
        'location': 'Private audit location', 'district': 'Alappuzha',
        'people_affected': 2, 'help_required': ['Rescue'],
    })
    assert response.status_code == 201, response.text
    incident = response.json()
    response = client.post(f'/api/incidents/{incident["id"]}/review',
                           headers=headers['admin'], json={'verified': verified})
    assert response.status_code == 200, response.text
    return incident


def dispatch(client, admin, incident, team):
    return client.post('/api/teams/assign', headers=admin,
                       json={'incident_id': incident['id'], 'team_id': team['id']})


def resolve(client, operator, incident):
    current = client.get(f'/api/incidents/{incident["id"]}', headers=operator).json()
    if current['status'] == 'team_assigned':
        accepted = client.post(f'/api/teams/assignments/{current["assignment"]["id"]}/accept', headers=operator)
        assert accepted.status_code == 200, accepted.text
    for state in ('en_route', 'in_progress', 'resolved'):
        response = client.post(f'/api/incidents/{incident["id"]}/status',
                               headers=operator, json={'status': state})
        assert response.status_code == 200, response.text


def test_rereview_of_completed_investigation_does_not_release_other_active_work(client, headers):
    team, operator = provision_team(client, headers['admin'], 'investigation')
    first = reviewed_report(client, headers, verified=False)
    assert dispatch(client, headers['admin'], first, team).status_code == 200
    findings = client.post(f'/api/investigation/{first["id"]}/report', headers=operator, json={
        'verified': True, 'people_affected': 2, 'required_items': ['Water'],
        'findings': 'Audit investigation confirmed a request for assistance.',
    })
    assert findings.status_code == 201, findings.text
    resolve(client, operator, first)
    second = reviewed_report(client, headers, verified=False)
    assert dispatch(client, headers['admin'], second, team).status_code == 200

    response = client.post(f'/api/incidents/{first["id"]}/review',
                           headers=headers['admin'], json={'verified': True})
    assert response.status_code == 200, response.text
    updated = next(row for row in client.get('/api/teams', headers=headers['admin']).json()
                   if row['id'] == team['id'])
    assert updated['available'] is False
    assert team['id'] not in [row['id'] for row in client.get('/api/teams/available', headers=operator).json()]
    third = reviewed_report(client, headers, verified=False)
    assert dispatch(client, headers['admin'], third, team).status_code == 409


def test_dispatch_checks_active_assignments_even_if_availability_flag_is_stale(client, headers):
    team, operator = provision_team(client, headers['admin'])
    first = reviewed_report(client, headers)
    assert dispatch(client, headers['admin'], first, team).status_code == 200
    # Simulate legacy inconsistent data in the isolated test database, never live data.
    from backend.database.connection import SessionLocal
    from backend.models.team import Team
    with SessionLocal() as db:
        db.get(Team, team['id']).available = True
        db.commit()
    second = reviewed_report(client, headers)
    assert team['id'] not in [row['id'] for row in client.get('/api/teams/available', headers=operator).json()]
    assert dispatch(client, headers['admin'], second, team).status_code == 409


def test_dashboard_counts_real_assigned_teams_not_manually_unavailable_teams(client, headers):
    before = client.get('/api/admin/dashboard', headers=headers['admin']).json()['teams_assigned']
    provision_team(client, headers['admin'], available=False)
    assert client.get('/api/admin/dashboard', headers=headers['admin']).json()['teams_assigned'] == before
    team, operator = provision_team(client, headers['admin'])
    incident = reviewed_report(client, headers)
    assert dispatch(client, headers['admin'], incident, team).status_code == 200
    assert client.get('/api/admin/dashboard', headers=headers['admin']).json()['teams_assigned'] == before + 1
    resolve(client, operator, incident)
    assert client.get('/api/admin/dashboard', headers=headers['admin']).json()['teams_assigned'] == before


@pytest.mark.parametrize('active,expiry,should_notify', [
    (False, None, False), (True, -1, False), (False, 1, False), (True, 1, True),
])
def test_alert_notifications_only_for_current_active_alerts(client, headers, active, expiry, should_notify):
    title = f'Audit visibility alert {uuid4().hex[:8]}'
    body = {'title': title, 'message': 'Synthetic audit notice, not an actual emergency.',
            'location': 'Chengannur', 'district': 'Alappuzha', 'active': active}
    if expiry is not None:
        body['expires_at'] = (datetime.now(timezone.utc) + timedelta(days=expiry)).isoformat()
    response = client.post('/api/alerts', headers=headers['admin'], json=body)
    assert response.status_code == 201, response.text
    alerts = client.get('/api/alerts').json()
    notices = client.get('/api/notifications', headers=headers['citizen']).json()
    assert (response.json()['id'] in [row['id'] for row in alerts]) is should_notify
    assert any(row['title'] == title for row in notices) is should_notify


def test_task_history_survives_reassignment_without_revealing_private_or_later_case_data(client, headers):
    investigator, investigation_auth = provision_team(client, headers['admin'], 'investigation')
    rescuer, rescue_auth = provision_team(client, headers['admin'])
    incident = reviewed_report(client, headers, verified=False)
    assert dispatch(client, headers['admin'], incident, investigator).status_code == 200
    assert client.post(f'/api/investigation/{incident["id"]}/report', headers=investigation_auth, json={
        'verified': True, 'people_affected': 2, 'required_items': ['Water'],
        'findings': 'Private field findings should not appear in task history.',
    }).status_code == 201
    assert client.post(f'/api/incidents/{incident["id"]}/review', headers=headers['admin'],
                       json={'verified': True}).status_code == 200
    assert dispatch(client, headers['admin'], incident, rescuer).status_code == 200
    assigned = client.get(f'/api/incidents/{incident["id"]}', headers=rescue_auth).json()
    assert client.post(f'/api/teams/assignments/{assigned["assignment"]["id"]}/accept', headers=rescue_auth).status_code == 200
    assert client.post(f'/api/incidents/{incident["id"]}/status', headers=rescue_auth,
                       json={'status': 'en_route'}).status_code == 200

    assert client.get(f'/api/incidents/{incident["id"]}', headers=investigation_auth).status_code == 403
    response = client.get('/api/teams/history', headers=investigation_auth)
    assert response.status_code == 200, response.text
    history = response.json()
    assert len(history) == 1
    row = history[0]
    assert set(row) == {'assignment_id', 'incident_id', 'reference', 'assigned_at', 'ended_at',
                        'assignment_status', 'last_status'}
    assert row['incident_id'] == incident['id'] and row['reference'] == incident['reference']
    assert row['assignment_status'] == 'released'
    assert row['last_status'] == 'team_assigned'  # The new rescue's en_route is excluded.
    assert row['ended_at'] is not None and row['assigned_at'].endswith('+00:00')
    encoded = json.dumps(history).lower()
    assert 'private' not in encoded and 'findings' not in encoded and 'citizen' not in encoded
    unrelated, unrelated_auth = provision_team(client, headers['admin'])
    assert client.get('/api/teams/history', headers=unrelated_auth).json() == []
    assert client.get('/api/teams/history').status_code == 401
    assert client.get('/api/teams/history', headers=headers['citizen']).status_code == 403
    assert client.get('/api/teams/history', headers=headers['admin']).status_code == 403


def test_completed_task_history_records_the_teams_own_end_and_status(client, headers):
    team, operator = provision_team(client, headers['admin'])
    incident = reviewed_report(client, headers)
    assert dispatch(client, headers['admin'], incident, team).status_code == 200
    current = client.get('/api/teams/history', headers=operator).json()[0]
    assert current['assignment_status'] == 'active' and current['ended_at'] is None
    resolve(client, operator, incident)
    finished = client.get('/api/teams/history', headers=operator).json()[0]
    assert finished['assignment_status'] == 'completed'
    assert finished['ended_at'] is not None and finished['last_status'] == 'resolved'


@pytest.mark.parametrize('path', ['create-payment', 'payment-success'])
def test_payment_paths_reject_incomplete_payment_payloads(client, headers, path):
    response = client.post(f'/api/donations/{path}', headers=headers['citizen'], json={'amount': 500})
    assert response.status_code == 422


def test_password_reset_delivery_is_explicitly_unavailable_outside_demo(client, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, 'demo_mode', False)
    response = client.post('/api/auth/forgot-password', json={'email': 'citizen@resq.local'})
    assert response.status_code == 503
    assert 'delivery is not configured' in response.json()['detail']
    assert 'demo_token' not in response.json()


def test_nearby_shelter_search_uses_coordinates_and_radius(client, headers):
    shelter = client.post('/api/shelters', headers=headers['admin'], json={
        'name': 'Audit exact-coordinate shelter', 'location': 'Audit point',
        'district': 'Alappuzha', 'capacity': 10, 'latitude': 9.0, 'longitude': 76.0,
    })
    assert shelter.status_code == 201, shelter.text
    near = client.get('/api/shelters/nearby', params={'latitude': 9.0, 'longitude': 76.0, 'radius_km': 1})
    assert near.status_code == 200
    row = next(row for row in near.json() if row['id'] == shelter.json()['id'])
    assert row['distance_km'] == 0 and row['available_capacity'] == 10
    far = client.get('/api/shelters/nearby', params={'latitude': 10.0, 'longitude': 76.0, 'radius_km': 1})
    assert shelter.json()['id'] not in [row['id'] for row in far.json()]
    assert client.get('/api/shelters/nearby', params={'latitude': 100, 'longitude': 76}).status_code == 422


def test_admin_report_aggregates_follow_incidents_relief_stock_shelters_and_pledges(client, headers):
    before = client.get('/api/admin/reports', headers=headers['admin']).json()
    incident = reviewed_report(client, headers)
    item = f'Audit report water {uuid4().hex[:8]}'
    stock = client.post('/api/relief/inventory', headers=headers['admin'], json={
        'item': item, 'quantity': 5, 'unit': 'bottles', 'location': 'Audit report hub',
    }).json()
    request = client.post('/api/relief/request', headers=headers['citizen'], json={
        'location': 'Audit report household', 'incident_id': incident['id'],
        'items': [{'item': item, 'quantity': 2}],
    }).json()
    assert client.post('/api/relief/distribution', headers=headers['admin'], json={
        'request_id': request['id'], 'inventory_id': stock['id'], 'quantity': 2,
    }).status_code == 201
    shelter = client.post('/api/shelters', headers=headers['admin'], json={
        'name': 'Audit report shelter', 'location': 'Audit point', 'district': 'Alappuzha',
        'capacity': 10, 'occupied': 3,
    }).json()
    campaign = client.post('/api/donations/campaigns', headers=headers['admin'], json={
        'title': 'Audit report support campaign', 'description': 'A synthetic pledge reporting example.',
        'target_amount': 1000,
    }).json()
    assert client.post('/api/donations/pledges', headers=headers['citizen'], json={
        'campaign_id': campaign['id'], 'kind': 'money', 'amount': 123.45,
    }).status_code == 201
    after = client.get('/api/admin/reports', headers=headers['admin']).json()
    assert after['incidents_by_status'].get('under_review', 0) == before['incidents_by_status'].get('under_review', 0) + 1
    assert after['relief_requests_by_status'].get('fulfilled', 0) == before['relief_requests_by_status'].get('fulfilled', 0) + 1
    assert after['distributions'] == before['distributions'] + 1
    assert next(row for row in after['inventory'] if row['id'] == stock['id'])['quantity'] == 3
    assert next(row for row in after['shelters'] if row['id'] == shelter['id'])['available_capacity'] == 7
    assert after['donations']['pledges'] == before['donations']['pledges'] + 1
    assert after['donations']['total_pledged_money'] == pytest.approx(before['donations']['total_pledged_money'] + 123.45)
    assert after['donations']['payment_status'] in {'offline', 'razorpay', 'sandbox'}


def test_flood_specific_version_rejects_unsupported_disaster_types(client, headers):
    body = {'message': 'A synthetic out-of-scope event report.', 'location': 'Audit location'}
    for kind in ('landslide', 'storm', 'other'):
        response = client.post('/api/incidents', headers=headers['citizen'],
                               json={**body, 'disaster_type': kind})
        assert response.status_code == 422, response.text
