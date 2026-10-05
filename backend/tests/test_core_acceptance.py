"""Acceptance regressions for secure recovery, receipts and operational records."""
import hashlib
import hmac
import os
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select, text

from backend.tests.conftest import auth


def new_pledge(client, headers, kind="money"):
    campaign_id = client.get('/api/donations/campaigns').json()[0]['id']
    payload = {'campaign_id': campaign_id, 'kind': kind}
    if kind == 'money':
        payload['amount'] = 123.45
    else:
        payload['items'] = [{'item': 'Acceptance blankets ' + uuid4().hex[:8], 'quantity': 3, 'unit': 'sets'}]
    response = client.post('/api/donations/pledges', headers=headers['citizen'], json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_recovery_is_private_and_single_use(client, headers):
    email = uuid4().hex + '@recovery.example'
    account = client.post('/api/auth/register', json={'name': 'Recovery user', 'email': email, 'password': 'RecoveryPass!2026'}).json()
    response = client.post('/api/auth/forgot-password', json={'email': email})
    assert response.status_code == 200 and set(response.json()) == {'message'}
    assert client.get('/api/admin/recovery-mail', headers=headers['citizen']).status_code == 403
    mail = next(row for row in client.get('/api/admin/recovery-mail', headers=headers['admin']).json() if row['recipient'] == email)
    token = parse_qs(urlsplit(mail['reset_url']).fragment.split('?', 1)[1])['token'][0]
    payload = {'token': token, 'password': 'ReplacementPass!2026'}
    assert client.post('/api/auth/reset-password', json=payload).status_code == 200
    assert client.post('/api/auth/reset-password', json=payload).status_code == 400
    assert client.get('/api/users/me', headers=auth(account)).status_code == 401


def test_smtp_recovery_works_without_public_token_or_demo_mail(client, headers, monkeypatch):
    from backend.config import settings
    from backend.services import auth_service
    sent = []
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self, **kwargs): pass
        def login(self, *args): pass
        def send_message(self, message): sent.append(message)
    monkeypatch.setattr(auth_service.smtplib, 'SMTP', SMTP)
    monkeypatch.setattr(settings, 'demo_mode', False)
    monkeypatch.setattr(settings, 'smtp_host', 'smtp.test.invalid')
    monkeypatch.setattr(settings, 'smtp_from', 'no-reply@example.org')
    response = client.post('/api/auth/forgot-password', json={'email': 'citizen@resq.local'})
    assert response.status_code == 200 and set(response.json()) == {'message'}
    assert sent and '/#/reset?token=' in sent[0].get_content()
    assert client.get('/api/admin/recovery-mail', headers=headers['admin']).status_code == 403


@pytest.mark.parametrize('kind,method', [('money', 'bank_transfer'), ('supplies', 'supplies')])
def test_offline_receipts_require_admin_and_are_idempotent(client, headers, kind, method):
    pledge = new_pledge(client, headers, kind)
    before = client.get('/api/admin/reports', headers=headers['admin']).json()['donations']
    path = f'/api/donations/{pledge["id"]}'
    assert client.post(path + '/verify', headers=headers['admin'], json={'approved': True}).status_code == 409
    submitted = client.post(path + '/submit-proof', headers=headers['citizen'], json={'method': method, 'reference': 'Confirmed receipt ' + uuid4().hex})
    assert submitted.status_code == 200 and submitted.json()['status'] == 'pending_verification'
    assert client.post(path + '/verify', headers=headers['citizen'], json={'approved': True}).status_code == 403
    verified = client.post(path + '/verify', headers=headers['admin'], json={'approved': True, 'note': 'Coordinator checked actual receipt'})
    assert verified.status_code == 200, verified.text
    receipt = verified.json()['receipt']
    assert verified.json()['status'] == 'received' and receipt['sandbox'] is False
    repeated = client.post(path + '/verify', headers=headers['admin'], json={'approved': True})
    assert repeated.json()['receipt']['id'] == receipt['id']
    after = client.get('/api/admin/reports', headers=headers['admin']).json()['donations']
    assert after['received_records'] == before['received_records'] + 1
    if kind == 'supplies':
        item = pledge['items'][0]['item']
        stock = next(row for row in client.get('/api/relief/inventory', headers=headers['admin']).json() if row['item'] == item)
        assert stock['quantity'] == 3 and stock['unit'] == 'sets'
    else:
        assert float(after['received_money']) == pytest.approx(float(before['received_money']) + 123.45)


def test_proof_ownership_and_rejected_resubmission(client, headers):
    pledge = new_pledge(client, headers)
    path = f'/api/donations/{pledge["id"]}'
    assert client.post(path + '/submit-proof', headers=headers['rescue'], json={'method': 'cash', 'reference': 'receipt-123'}).status_code == 403
    assert client.post(path + '/submit-proof', headers=headers['citizen'], json={'method': 'supplies', 'reference': 'receipt-123'}).status_code == 422
    assert client.post(path + '/submit-proof', headers=headers['citizen'], json={'method': 'cash', 'reference': 'receipt-123'}).status_code == 200
    assert client.post(path + '/verify', headers=headers['admin'], json={'approved': False, 'note': 'Please correct receipt'}).json()['status'] == 'rejected'
    assert client.post(path + '/submit-proof', headers=headers['citizen'], json={'method': 'cash', 'reference': 'receipt-corrected'}).status_code == 200


def test_sandbox_never_counts_as_received_money(client, headers, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, 'payment_provider', 'sandbox')
    pledge = new_pledge(client, headers)
    before = client.get('/api/admin/reports', headers=headers['admin']).json()['donations']
    order = client.post('/api/donations/create-payment', headers=headers['citizen'], json={'pledge_id': pledge['id']})
    assert order.status_code == 201 and order.json()['sandbox'] is True
    path = f'/api/donations/payments/{order.json()["transaction_id"]}/simulate'
    receipt = client.post(path, headers=headers['citizen'])
    assert receipt.status_code == 200 and receipt.json()['status'] == 'sandbox_completed'
    assert client.post(path, headers=headers['citizen']).json()['receipt']['id'] == receipt.json()['receipt']['id']
    after = client.get('/api/admin/reports', headers=headers['admin']).json()['donations']
    assert after['received_money'] == before['received_money'] and after['received_records'] == before['received_records']
    assert after['sandbox_records'] == before['sandbox_records'] + 1
    monkeypatch.setattr(settings, 'demo_mode', False)
    assert client.post(path, headers=headers['citizen']).status_code == 403


def test_razorpay_requires_signature_exact_capture_and_is_idempotent(client, headers, monkeypatch):
    from backend.config import settings
    from backend.routers import donations
    monkeypatch.setattr(settings, 'payment_provider', 'razorpay')
    monkeypatch.setattr(settings, 'razorpay_key_id', 'rzp_test_acceptance')
    monkeypatch.setattr(settings, 'razorpay_key_secret', 'isolated-test-secret')
    order_id = 'order_' + uuid4().hex
    payment_id = 'pay_' + uuid4().hex
    captured = {'id': payment_id, 'order_id': order_id, 'amount': 12345, 'currency': 'INR', 'status': 'authorized'}
    def provider(method, path, payload=None):
        if method == 'POST':
            assert payload['amount'] == 12345
            return {'id': order_id, 'amount': 12345, 'currency': 'INR'}
        return dict(captured)
    monkeypatch.setattr(donations, 'razorpay_request', provider)
    pledge = new_pledge(client, headers)
    response = client.post('/api/donations/create-payment', headers=headers['citizen'], json={'pledge_id': pledge['id']})
    assert response.status_code == 201
    payload = {'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': '0' * 64}
    assert client.post('/api/donations/payment-success', headers=headers['citizen'], json=payload).status_code == 400
    payload['razorpay_signature'] = hmac.new(settings.razorpay_key_secret.encode(), (order_id + '|' + payment_id).encode(), hashlib.sha256).hexdigest()
    assert client.post('/api/donations/payment-success', headers=headers['rescue'], json=payload).status_code == 403
    assert client.post('/api/donations/payment-success', headers=headers['citizen'], json=payload).status_code == 409
    captured['status'] = 'captured'
    captured['currency'] = 'USD'
    assert client.post('/api/donations/payment-success', headers=headers['citizen'], json=payload).status_code == 409
    captured['currency'] = 'INR'
    success = client.post('/api/donations/payment-success', headers=headers['citizen'], json=payload)
    assert success.status_code == 200 and success.json()['receipt']['sandbox'] is True
    assert client.post('/api/donations/payment-success', headers=headers['citizen'], json=payload).json()['receipt']['id'] == success.json()['receipt']['id']


def test_news_requires_verification_and_edits_invalidate_it(client, headers):
    row = client.post('/api/news', headers=headers['admin'], json={'title': 'Acceptance verified article', 'content': 'Coordinator reviewed this synthetic content.'}).json()
    path = f'/api/news/{row["id"]}'
    assert client.put(path, headers=headers['admin'], json={'published': True}).status_code == 409
    assert client.post(path + '/verify', headers=headers['citizen'], json={'note': 'Unauthorized'}).status_code == 403
    assert client.post(path + '/verify', headers=headers['admin'], json={'note': 'Checked source'}).json()['verified'] is True
    assert client.put(path, headers=headers['admin'], json={'published': True}).status_code == 200
    edited = client.put(path, headers=headers['admin'], json={'content': 'Changed article requires another coordinator review.'})
    assert edited.json()['verified'] is False and edited.json()['published'] is False


def test_shelter_status_history_and_type_dependency(client, headers):
    team = client.post('/api/teams', headers=headers['admin'], json={'name': 'Acceptance shelter team', 'team_type': 'shelter', 'district': 'Alappuzha'}).json()
    shelter = client.post('/api/shelters', headers=headers['admin'], json={'name': 'Acceptance shelter', 'location': 'Audit point', 'district': 'Alappuzha', 'capacity': 20, 'occupied': 5, 'team_id': team['id'], 'latitude': 9, 'longitude': 76}).json()
    assert client.put(f'/api/teams/{team["id"]}', headers=headers['admin'], json={'team_type': 'relief'}).status_code == 409
    closed = client.put(f'/api/shelters/{shelter["id"]}', headers=headers['admin'], json={'status': 'closed'})
    assert closed.json()['available_capacity'] == 0
    nearby = client.get('/api/shelters/nearby', params={'latitude': 9, 'longitude': 76, 'radius_km': 1}).json()
    assert shelter['id'] not in [row['id'] for row in nearby]
    history = client.get(f'/api/shelters/{shelter["id"]}/history', headers=headers['admin']).json()
    assert len(history['updates']) == 2 and len(history['occupancy']) == 2
    assert history['updates'][-1]['snapshot']['status'] == 'closed'


def test_acceptance_records_actor_and_blocks_skip(client, headers, incident):
    team_id = client.get('/api/users/me', headers=headers['rescue']).json()['team_id']
    assert client.post(f'/api/incidents/{incident["id"]}/review', headers=headers['admin'], json={'verified': True}).status_code == 200
    assigned = client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': incident['id'], 'team_id': team_id}).json()
    assert client.post(f'/api/incidents/{incident["id"]}/status', headers=headers['rescue'], json={'status': 'en_route'}).status_code == 409
    path = f'/api/teams/assignments/{assigned["assignment"]["id"]}/accept'
    assert client.post(path, headers=headers['citizen']).status_code == 403
    accepted = client.post(path, headers=headers['rescue'])
    assert accepted.status_code == 200 and accepted.json()['status'] == 'task_accepted'
    assert accepted.json()['assignment']['accepted_at'] is not None
    assert client.post(path, headers=headers['rescue']).json()['assignment']['accepted_at'] == accepted.json()['assignment']['accepted_at']
    for state in ('en_route', 'in_progress', 'resolved'):
        assert client.post(f'/api/incidents/{incident["id"]}/status', headers=headers['rescue'], json={'status': state}).status_code == 200


def test_normalized_memberships_follow_admin_account_changes(client, headers):
    from backend.database.connection import SessionLocal
    from backend.database.models import RoleRecord, TeamMember, UserRole
    team_id = client.get('/api/users/me', headers=headers['shelter']).json()['team_id']
    user = client.post('/api/admin/users', headers=headers['admin'], json={'name': 'Acceptance member', 'email': uuid4().hex + '@membership.example', 'password': 'MembershipPass!2026', 'role': 'response_team', 'team_id': team_id}).json()
    with SessionLocal() as db:
        assert db.get(TeamMember, (user['id'], team_id))
        assert db.scalar(select(RoleRecord.name).join(UserRole).where(UserRole.user_id == user['id'])) == 'response_team'
    assert client.put(f'/api/admin/users/{user["id"]}', headers=headers['admin'], json={'role': 'citizen'}).status_code == 200
    with SessionLocal() as db:
        assert not db.scalar(select(TeamMember).where(TeamMember.user_id == user['id']))
        assert db.scalar(select(RoleRecord.name).join(UserRole).where(UserRole.user_id == user['id'])) == 'citizen'


def test_legacy_sqlite_migration_preserves_records_and_relaxes_unknown_count(tmp_path):
    from backend.database.migrations import migrate_schema
    engine = create_engine('sqlite:///' + str(tmp_path / 'legacy.db'))
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, email VARCHAR(254) NOT NULL UNIQUE, password_hash VARCHAR(256) NOT NULL, role VARCHAR(20) NOT NULL, district VARCHAR(80) NOT NULL, team_id INTEGER, active BOOLEAN NOT NULL, created_at DATETIME NOT NULL)'))
        connection.execute(text("INSERT INTO users VALUES (1, 'Historical owner', 'history@example.org', 'unused-fixture-hash', 'citizen', 'Ernakulam', NULL, 1, '2026-10-03')"))
        connection.execute(text('CREATE TABLE incident_reports (id INTEGER PRIMARY KEY, reference VARCHAR(30) UNIQUE NOT NULL, user_id INTEGER NOT NULL, message TEXT NOT NULL, location VARCHAR(200) NOT NULL, district VARCHAR(80) NOT NULL, latitude FLOAT, longitude FLOAT, people_affected INTEGER NOT NULL, help_required JSON NOT NULL, disaster_type VARCHAR(50) NOT NULL, status VARCHAR(30) NOT NULL, severity VARCHAR(20) NOT NULL, verified BOOLEAN, photo_url VARCHAR(300), created_at DATETIME NOT NULL)'))
        connection.execute(text("INSERT INTO incident_reports VALUES (7, 'RQ-PRESERVE', 1, 'Historical synthetic report', 'Aluva', 'Ernakulam', NULL, NULL, 4, '[]', 'flood', 'submitted', 'pending', NULL, NULL, '2026-10-03')"))
    migrate_schema(engine)
    migrate_schema(engine)
    with engine.begin() as connection:
        assert connection.execute(text('SELECT reference,people_affected FROM incident_reports WHERE id=7')).one() == ('RQ-PRESERVE', 4)
        connection.execute(text('UPDATE incident_reports SET people_affected=NULL, location=NULL WHERE id=7'))
    original = {'users','roles','user_roles','refresh_tokens','incident_reports','report_analysis','disaster_types','severity_predictions','alerts','alert_matches','teams','team_members','assignments','investigation_reports','status_history','inventory','relief_requests','distributions','shelters','shelter_updates','shelter_occupancy','notifications','news','safety_tips','chat_sessions','chat_messages','donation_campaigns','donations','payment_transactions','audit_logs'}
    assert original <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_legacy_database_migration_preserves_domain_rows(tmp_path):
    """Use an isolated PostgreSQL schema when the suite selects its test database."""
    from backend.database.migrations import migrate_schema, backfill_domain_records
    from sqlalchemy.orm import Session
    url = os.getenv('TEST_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'legacy-domain.db'))
    schema = 'acceptance_' + uuid4().hex
    admin_engine = None
    if url.startswith('postgresql'):
        # Never create fixtures in the operational application's schema/database.
        from sqlalchemy.engine import make_url
        database = make_url(url).database
        assert database and ('test' in database or database.startswith('resq_core_acceptance'))
        admin_engine = create_engine(url)
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={'options': f'-c search_path={schema}'})
        timestamp_type = 'TIMESTAMP WITH TIME ZONE'
    else:
        engine = create_engine(url)
        timestamp_type = 'DATETIME'
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, email VARCHAR(254) NOT NULL UNIQUE, password_hash VARCHAR(256) NOT NULL, role VARCHAR(20) NOT NULL, district VARCHAR(80) NOT NULL, team_id INTEGER, active BOOLEAN NOT NULL, created_at {timestamp_type} NOT NULL)'))
            connection.execute(text("INSERT INTO users VALUES (1, 'Historical owner', 'history@example.org', 'unused-fixture-hash', 'citizen', 'Ernakulam', NULL, :active, '2026-10-03')"), {'active': True})
            connection.execute(text(f'CREATE TABLE incident_reports (id INTEGER PRIMARY KEY, reference VARCHAR(30) UNIQUE NOT NULL, user_id INTEGER NOT NULL, message TEXT NOT NULL, location VARCHAR(200) NOT NULL, district VARCHAR(80) NOT NULL, latitude FLOAT, longitude FLOAT, people_affected INTEGER NOT NULL, help_required JSON NOT NULL, disaster_type VARCHAR(50) NOT NULL, status VARCHAR(30) NOT NULL, severity VARCHAR(20) NOT NULL, verified BOOLEAN, photo_url VARCHAR(300), created_at {timestamp_type} NOT NULL)'))
            connection.execute(text("INSERT INTO incident_reports VALUES (7, 'RQ-LEGACY-DOMAIN', 1, 'Historical message preserved', 'Aluva', 'Ernakulam', NULL, NULL, 4, '[]', 'flood', 'submitted', 'pending', NULL, NULL, '2026-10-03')"))
        from sqlalchemy import MetaData, Table
        from backend.database.connection import Base
        from backend.database import models
        from backend.database.migrations.acceptance import ADDITIONS
        old_names = {'users','refresh_tokens','password_resets','notifications','audit_logs','chat_messages','teams','incident_reports','report_analysis','status_history','assignments','investigation_reports','alerts','news','safety_tips','shelters','inventory','relief_requests','distributions','donation_campaigns','donation_pledges'}
        old = MetaData()
        for name in old_names:
            Table(name, old, *(column._copy() for column in Base.metadata.tables[name].columns if column.name not in ADDITIONS.get(name, {})))
        old.create_all(engine)
        with engine.begin() as connection:
            connection.execute(old.tables['teams'].insert(), {'id': 1, 'name': 'Preserved shelter team', 'team_type': 'shelter', 'district': 'Ernakulam', 'available': True})
            connection.execute(old.tables['inventory'].insert(), {'id': 1, 'item': 'Historical water', 'quantity': 9, 'unit': 'bottles', 'location': 'Preserved hub'})
            connection.execute(old.tables['relief_requests'].insert(), {'id': 1, 'user_id': 1, 'incident_id': 7, 'items': [{'item': 'Historical water', 'quantity': 2}], 'location': 'Aluva'})
            connection.execute(old.tables['distributions'].insert(), {'id': 1, 'request_id': 1, 'inventory_id': 1, 'quantity': 1, 'actor_id': 1})
            connection.execute(old.tables['shelters'].insert(), {'id': 1, 'name': 'Preserved shelter', 'location': 'Aluva', 'district': 'Ernakulam', 'capacity': 25, 'occupied': 7, 'team_id': 1})
            connection.execute(old.tables['news'].insert(), {'id': 1, 'title': 'Previously published article', 'content': 'Preserve prior administrator-approved content', 'published': True})
            connection.execute(old.tables['chat_messages'].insert(), {'id': 1, 'user_id': 1, 'message': 'Historical question', 'answer': 'Historical answer'})
            connection.execute(old.tables['donation_campaigns'].insert(), {'id': 1, 'title': 'Preserved campaign', 'description': 'Historical campaign records', 'target_amount': 500})
            connection.execute(old.tables['donation_pledges'].insert(), {'id': 1, 'campaign_id': 1, 'user_id': 1, 'kind': 'money', 'amount': 12.34})
            connection.execute(old.tables['report_analysis'].insert(), {'id': 1, 'incident_id': 7, 'result': {'severity': 'HIGH', 'confidence': 0.5, 'alert_match': {'status': 'NO_MATCH'}}})
        migrate_schema(engine)
        with Session(engine) as db:
            backfill_domain_records(db)
            db.commit()
        migrate_schema(engine)
        with engine.begin() as connection:
            assert connection.execute(text('SELECT reference,message,people_affected FROM incident_reports WHERE id=7')).one() == ('RQ-LEGACY-DOMAIN', 'Historical message preserved', 4)
            assert connection.execute(text('SELECT COUNT(*) FROM user_roles WHERE user_id=1')).scalar() == 1
            assert connection.execute(text('SELECT disaster_type_id FROM incident_reports WHERE id=7')).scalar() is not None
            assert connection.execute(text('SELECT item,unit,quantity FROM distributions WHERE id=1')).one() == ('Historical water', 'bottles', 1)
            assert connection.execute(text('SELECT occupied,capacity FROM shelters WHERE id=1')).one() == (7, 25)
            assert connection.execute(text('SELECT COUNT(*) FROM shelter_updates WHERE shelter_id=1')).scalar() == 1
            assert connection.execute(text('SELECT COUNT(*) FROM shelter_occupancy WHERE shelter_id=1')).scalar() == 1
            assert connection.execute(text('SELECT session_id FROM chat_messages WHERE id=1')).scalar() is not None
            assert connection.execute(text('SELECT message,answer FROM chat_messages WHERE id=1')).one() == ('Historical question', 'Historical answer')
            assert connection.execute(text('SELECT amount,status FROM donation_pledges WHERE id=1')).one() == (12.34, 'pledged')
            assert connection.execute(text('SELECT verified,published FROM news WHERE id=1')).one() == (True, True)
            assert connection.execute(text('SELECT COUNT(*) FROM severity_predictions WHERE incident_id=7')).scalar() == 1
            assert connection.execute(text('SELECT COUNT(*) FROM alert_matches WHERE incident_id=7')).scalar() == 1
            connection.execute(text('UPDATE incident_reports SET people_affected=NULL,location=NULL WHERE id=7'))
        assert len(inspect(engine).get_table_names()) == 33
    finally:
        engine.dispose()
        if admin_engine is not None:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin_engine.dispose()


def test_clarification_remains_open_until_facts_resolve_and_survives_reanalysis(client, headers, monkeypatch):
    from backend.database.connection import SessionLocal
    from backend.models.incident import AlertMatch, SeverityPrediction
    calls = []
    async def analyze(**payload):
        calls.append(payload)
        landmark = next((answer.get('landmark') for answer in reversed(payload['clarification_answers']) if answer.get('landmark')), None)
        return {
            'analysis_status': 'completed', 'severity': 'MODERATE', 'confidence': .5,
            'extracted_location': 'Chengannur', 'district': 'Alappuzha', 'people_affected': 12,
            'required_assistance': ['Water'], 'summary': 'Twelve people need drinking water.',
            'alert_match': {'status': 'NO_MATCH', 'alert_ids': []},
            'clarification': {'status': 'resolved' if landmark else 'open',
                              'question': None if landmark else 'What is your nearest landmark?',
                              'missing_fields': [] if landmark else ['ward_or_landmark']},
            'clarification_question': None if landmark else 'What is your nearest landmark?',
        }
    monkeypatch.setattr('backend.ai.agent.analyze_report', analyze)
    created = client.post('/api/incidents', headers=headers['citizen'], json={'message': 'Twelve people need water in Chengannur.'})
    assert created.status_code == 201, created.text
    row = created.json()
    assert (row['location'], row['district'], row['people_affected'], row['help_required']) == ('Chengannur', 'Alappuzha', 12, ['Water'])
    path = f'/api/incidents/{row["id"]}/clarification-reply'
    incomplete = client.post(path, headers=headers['citizen'], json={'answer': 'I still do not know the landmark.', 'people_affected': None})
    assert incomplete.status_code == 200, incomplete.text
    assert incomplete.json()['clarification']['status'] == 'open'
    assert incomplete.json()['clarification']['missing_fields'] == ['ward_or_landmark']
    completed = client.post(path, headers=headers['citizen'], json={'answer': 'We are beside the public bus station.', 'landmark': 'Public bus station'})
    assert completed.status_code == 200, completed.text
    assert completed.json()['clarification']['status'] == 'answered'
    assert completed.json()['analysis']['clarification_answers'][-1]['landmark'] == 'Public bus station'
    assert client.post(f'/api/incidents/{row["id"]}/analyze', headers=headers['admin']).status_code == 202
    assert calls[-1]['clarification_answers'][-1]['landmark'] == 'Public bus station'
    admin = client.get(f'/api/incidents/{row["id"]}', headers=headers['admin']).json()
    citizen = client.get(f'/api/incidents/{row["id"]}', headers=headers['citizen']).json()
    assert len(admin['analysis_history']) == 4 and 'analysis_history' not in citizen
    with SessionLocal() as db:
        assert len(list(db.scalars(select(SeverityPrediction).where(SeverityPrediction.incident_id == row['id'])))) == 4
        assert len(list(db.scalars(select(AlertMatch).where(AlertMatch.incident_id == row['id'])))) == 4


@pytest.mark.parametrize('other_work', [False, True])
def test_handoff_releases_moved_request_team_but_preserves_other_work(client, headers, incident, other_work):
    from backend.tests.test_extended import new_team
    from backend.tests.test_incident_acceptance import advance
    from backend.database.connection import SessionLocal
    from backend.models.inventory import ReliefRequest
    from backend.models.team import Team
    rescue, rescuer = new_team(client, headers['admin'], 'rescue')
    previous, _ = new_team(client, headers['admin'], 'relief')
    replacement, _ = new_team(client, headers['admin'], 'relief')
    ident = incident['id']
    assert client.post(f'/api/incidents/{ident}/review', headers=headers['admin'], json={'verified': True}).status_code == 200
    assert client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': ident, 'team_id': rescue['id']}).status_code == 200
    advance(client, rescuer, incident, ['en_route', 'in_progress'])
    request = client.post('/api/relief/request', headers=headers['citizen'], json={
        'incident_id': ident, 'location': 'Chengannur', 'items': [{'item': 'Water', 'quantity': 2, 'unit': 'bottles'}],
    }).json()
    assigned = client.post(f'/api/relief/requests/{request["id"]}/assign', headers=headers['admin'], json={'team_id': previous['id'], 'note': 'Deliver the requested supplies.'})
    assert assigned.status_code == 200, assigned.text
    if other_work:
        with SessionLocal() as db:
            db.add(ReliefRequest(user_id=incident['user_id'], assigned_team_id=previous['id'], items=[{'item': 'Blankets', 'quantity': 1, 'unit': 'pieces'}], location='Another household', status='assigned'))
            db.commit()
    response = client.post(f'/api/incidents/{ident}/handoff', headers=headers['admin'], json={'team_id': replacement['id'], 'note': 'Transfer supplies to the replacement relief team.'})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert db.get(ReliefRequest, request['id']).assigned_team_id == replacement['id']
        assert db.get(Team, previous['id']).available is (not other_work)
        assert db.get(Team, rescue['id']).available is True
        assert db.get(Team, replacement['id']).available is False
    assert client.get(f'/api/incidents/{ident}', headers=rescuer).status_code == 403


def test_open_linked_relief_blocks_resolution_and_finished_cases_use_independent_requests(client, headers, incident):
    from backend.tests.test_extended import new_team
    from backend.tests.test_incident_acceptance import advance
    from backend.database.connection import SessionLocal
    from backend.models.inventory import ReliefRequest
    rescue, rescuer = new_team(client, headers['admin'], 'rescue')
    ident = incident['id']
    assert client.post(f'/api/incidents/{ident}/review', headers=headers['admin'], json={'verified': True}).status_code == 200
    assert client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': ident, 'team_id': rescue['id']}).status_code == 200
    advance(client, rescuer, incident, ['en_route', 'in_progress'])
    payload = {'incident_id': ident, 'location': 'Chengannur', 'items': [{'item': 'Blankets', 'quantity': 1, 'unit': 'pieces'}]}
    request = client.post('/api/relief/request', headers=headers['citizen'], json=payload).json()
    path = f'/api/incidents/{ident}/status'
    assert client.post(path, headers=rescuer, json={'status': 'resolved'}).status_code == 409
    # Historical cancelled work must not block completion indefinitely.
    with SessionLocal() as db:
        db.get(ReliefRequest, request['id']).status = 'cancelled'
        db.commit()
    assert client.post(path, headers=rescuer, json={'status': 'resolved'}).status_code == 200
    assert client.post('/api/relief/request', headers=headers['citizen'], json=payload).status_code == 409
    assert client.post(path, headers=headers['admin'], json={'status': 'closed'}).status_code == 200
    assert client.post('/api/relief/request', headers=headers['citizen'], json=payload).status_code == 409
    payload.pop('incident_id')
    assert client.post('/api/relief/request', headers=headers['citizen'], json=payload).status_code == 201


@pytest.mark.parametrize('kind', ['supplies', 'rescue_support'])
@pytest.mark.parametrize('other_work', [False, True])
def test_standalone_completion_keeps_team_busy_only_for_remaining_work(client, headers, kind, other_work):
    from backend.tests.test_extended import new_team
    from backend.database.connection import SessionLocal
    from backend.models.inventory import ReliefRequest
    from backend.models.team import Team
    team, operator = new_team(client, headers['admin'], 'relief' if kind == 'supplies' else 'rescue')
    payload = {'kind': kind, 'location': 'Standalone household', 'items': [] if kind == 'rescue_support' else [{'item': 'Review water ' + uuid4().hex[:8], 'quantity': 2, 'unit': 'bottles'}]}
    request = client.post('/api/relief/request', headers=headers['citizen'], json=payload).json()
    assigned = client.post(f'/api/relief/requests/{request["id"]}/assign', headers=headers['admin'], json={'team_id': team['id'], 'note': 'Respond to this household request.'})
    assert assigned.status_code == 200, assigned.text
    if other_work:
        with SessionLocal() as db:
            db.add(ReliefRequest(user_id=request['user_id'], assigned_team_id=team['id'], kind=kind, items=payload['items'], location='Other household', status='assigned'))
            db.commit()
    if kind == 'rescue_support':
        response = client.post(f'/api/relief/requests/{request["id"]}/complete', headers=operator, json={'note': 'Evacuation assistance completed.'})
    else:
        stock = client.post('/api/relief/inventory', headers=headers['admin'], json={**payload['items'][0], 'location': 'Depot'}).json()
        response = client.post('/api/relief/distribution', headers=operator, json={'request_id': request['id'], 'inventory_id': stock['id'], 'quantity': 2})
    assert response.status_code in (200, 201), response.text
    with SessionLocal() as db:
        assert db.get(ReliefRequest, request['id']).status == 'fulfilled'
        assert db.get(Team, team['id']).available is (not other_work)


def test_chat_prioritizes_old_references_without_private_context_and_uses_shelter_status(client, headers, monkeypatch):
    from backend.tests.test_extended import register_citizen
    from backend.database.connection import SessionLocal
    from backend.models.incident import Incident
    citizen_id = client.get('/api/users/me', headers=headers['citizen']).json()['id']
    _, foreign_session = register_citizen(client)
    foreign_id = foreign_session['user']['id']
    prefix = 'RQ-OLD-' + uuid4().hex[:8].upper()
    with SessionLocal() as db:
        oldest = Incident(user_id=citizen_id, reference=prefix, message='Old owned report', location='Old landmark', district='Alappuzha')
        private = Incident(user_id=foreign_id, reference='RQ-PRIVATE-' + uuid4().hex[:8].upper(), message='PRIVATE report text', location='PRIVATE address', district='Alappuzha')
        db.add_all([oldest, private])
        for index in range(12):
            db.add(Incident(user_id=citizen_id, reference='RQ-NEW-' + uuid4().hex[:8].upper(), message='Recent owned report', location='Latest place', district='Alappuzha'))
        db.commit()
        oldest_id, private_id, private_reference = oldest.id, private.id, private.reference
    shelter_ids = []
    for status in ('closed', 'full'):
        shelter = client.post('/api/shelters', headers=headers['admin'], json={'name': prefix + ' ' + status, 'location': prefix, 'district': 'Alappuzha', 'capacity': 20, 'occupied': 2, 'status': status}).json()
        shelter_ids.append(shelter['id'])
    captured = []
    async def answer(message, context):
        captured.append(context)
        return {'answer': prefix + ': submitted', 'sources': [], 'status': 'completed'}
    monkeypatch.setattr('backend.ai.chatbot.answer_question', answer)
    first = client.post('/api/chatbot/chat', headers=headers['citizen'], json={'message': f'What is report {prefix} status and shelter capacity?'}).json()
    assert captured[-1]['incidents'][0]['id'] == oldest_id
    for shelter_id in shelter_ids:
        assert next(row for row in captured[-1]['shelters'] if row['id'] == shelter_id)['available_capacity'] == 0
    followup = client.post('/api/chatbot/chat', headers=headers['citizen'], json={'message': 'What is its assigned team?', 'session_id': first['session_id']})
    assert followup.status_code == 200 and captured[-1]['incidents'][0]['id'] == oldest_id
    assert client.post('/api/chatbot/chat', headers=headers['citizen'], json={'message': f'Show report {private_reference} case #{private_id} status'}).status_code == 200
    assert private_id not in [row['id'] for row in captured[-1]['incidents']]
    assert 'PRIVATE address' not in str(captured[-1]) and 'PRIVATE report text' not in str(captured[-1])


def test_duplicate_trace_and_analysis_history_are_admin_only(client, headers, incident):
    from backend.tests.test_extended import new_team
    from backend.database.connection import SessionLocal
    from backend.models.incident import Incident
    team, operator = new_team(client, headers['admin'], 'rescue')
    ident = incident['id']
    assert client.post(f'/api/incidents/{ident}/review', headers=headers['admin'], json={'verified': True}).status_code == 200
    assert client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': ident, 'team_id': team['id']}).status_code == 200
    with SessionLocal() as db:
        analysis = db.get(Incident, ident).analysis
        private = {'duplicate_candidates': [{'id': 987654, 'message': 'Other owner private text'}], 'duplicate_ids': [987654], 'tool_trace': [{'name': 'find_duplicates', 'status': 'completed', 'output': [{'id': 987654, 'message': 'Other owner private text'}]}]}
        analysis.result = {**analysis.result, **private}
        analysis.history = [{'result': private}]
        db.commit()
    for role_headers in (headers['citizen'], operator):
        record = client.get(f'/api/incidents/{ident}', headers=role_headers).json()
        assert 'analysis_history' not in record
        assert 'duplicate_ids' not in record['analysis'] and 'duplicate_candidates' not in record['analysis']
        assert 'output' not in record['analysis']['tool_trace'][0]
        assert '987654' not in str(record) and 'Other owner private text' not in str(record)
    admin = client.get(f'/api/incidents/{ident}', headers=headers['admin']).json()
    assert admin['analysis']['tool_trace'][0]['output'][0]['id'] == 987654 and admin['analysis_history']


def test_locked_read_refreshes_state_after_competing_writer(client, headers):
    from backend.database.connection import SessionLocal
    from backend.models.inventory import Inventory
    from backend.utils.validators import get_row
    stock = client.post('/api/relief/inventory', headers=headers['admin'], json={'item': 'Concurrent inventory state', 'quantity': 9, 'unit': 'pieces', 'location': 'Depot'}).json()
    with SessionLocal() as reader:
        stale = reader.get(Inventory, stock['id'])
        assert stale.quantity == 9
        with SessionLocal() as writer:
            writer.get(Inventory, stock['id']).quantity = 3
            writer.commit()
        assert get_row(reader, Inventory, stock['id'], lock=True).quantity == 3


def test_smtp_failure_does_not_disclose_account_existence(client, headers, monkeypatch):
    from backend.config import settings
    from backend.services import auth_service
    def unavailable(*args, **kwargs):
        raise OSError('Isolated SMTP test outage')
    monkeypatch.setattr(auth_service.smtplib, 'SMTP', unavailable)
    monkeypatch.setattr(settings, 'demo_mode', False)
    monkeypatch.setattr(settings, 'smtp_host', 'smtp.test.invalid')
    monkeypatch.setattr(settings, 'smtp_from', 'no-reply@example.org')
    known = client.post('/api/auth/forgot-password', json={'email': 'citizen@resq.local'})
    unknown = client.post('/api/auth/forgot-password', json={'email': uuid4().hex + '@unknown.example'})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json() and set(known.json()) == {'message'}


@pytest.mark.parametrize('location', ['ചെങ്ങന്നൂർ', 'Chengannoor'])
def test_monitoring_counts_current_alias_match_without_model_calls(client, headers, monkeypatch, location):
    from backend.database.connection import SessionLocal
    from backend.models.incident import Incident, ReportAnalysis
    alert = client.post('/api/alerts', headers=headers['admin'], json={'title': 'Monitoring alias ' + uuid4().hex[:8], 'message': 'Synthetic monitoring regression', 'location': 'Chengannur', 'district': 'Alappuzha'}).json()
    def count():
        return next(row for row in client.get('/api/admin/monitoring', headers=headers['admin']).json() if row['alert_id'] == alert['id'])
    before = count()['report_count']
    citizen_id = client.get('/api/users/me', headers=headers['citizen']).json()['id']
    with SessionLocal() as db:
        report = Incident(user_id=citizen_id, reference='RQ-MON-' + uuid4().hex[:8], message='വെള്ളപ്പൊക്കത്തിൽ സഹായം വേണം.', location=location, district='ആലപ്പുഴ')
        report.analysis = ReportAnalysis(result={'analysis_status': 'completed', 'extracted_location': location, 'district': 'Alappuzha', 'alert_match': {'status': 'MATCH', 'matched_alert_ids': [alert['id']]}})
        db.add(report)
        db.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError('Monitoring cannot call a model or external geocoder')
    monkeypatch.setattr('backend.ai.agent.analyze_report', forbidden)
    monkeypatch.setattr('backend.ai.location_extractor.resolve_geography', forbidden)
    current = count()
    assert current['report_count'] == before + 1 and current['status'] == 'reports_received'


@pytest.mark.parametrize('scenario', ['current_no_match', 'stale_current_match', 'pending_old_match', 'district_conflict'])
def test_monitoring_ignores_historical_or_stale_matches_and_district_conflicts(client, headers, scenario):
    from backend.database.connection import SessionLocal
    from backend.models.incident import Incident, ReportAnalysis
    alert = client.post('/api/alerts', headers=headers['admin'], json={'title': 'Monitoring stale ' + uuid4().hex[:8], 'message': 'Synthetic monitoring regression', 'location': 'Chengannur', 'district': 'Alappuzha'}).json()
    def count():
        return next(row for row in client.get('/api/admin/monitoring', headers=headers['admin']).json() if row['alert_id'] == alert['id'])['report_count']
    before = count()
    citizen_id = client.get('/api/users/me', headers=headers['citizen']).json()['id']
    old = {'analysis_status': 'completed', 'extracted_location': 'Chengannur', 'district': 'Alappuzha', 'alert_match': {'status': 'MATCH', 'matched_alert_ids': [alert['id']]}}
    current = dict(old)
    location, district = 'Cherthala', 'Alappuzha'
    if scenario == 'current_no_match':
        current = {**old, 'extracted_location': location, 'alert_match': {'status': 'NO_MATCH', 'matched_alert_ids': []}}
    elif scenario == 'pending_old_match':
        location = 'New unconfirmed landmark'
        current['analysis_status'] = 'pending'
    elif scenario == 'district_conflict':
        location, district = 'ചെങ്ങന്നൂർ', 'Ernakulam'
    with SessionLocal() as db:
        report = Incident(user_id=citizen_id, reference='RQ-STALE-' + uuid4().hex[:8], message='Original report mentioned Chengannur; current structured location changed.', location=location, district=district)
        report.analysis = ReportAnalysis(result=current, history=[{'result': old}])
        db.add(report)
        db.commit()
    assert count() == before


def test_monitoring_current_link_can_use_unchanged_unknown_alias_and_unanalysed_message(client, headers):
    from backend.database.connection import SessionLocal
    from backend.models.incident import Incident, ReportAnalysis
    alert = client.post('/api/alerts', headers=headers['admin'], json={'title': 'Monitoring links ' + uuid4().hex[:8], 'message': 'Synthetic monitoring regression', 'location': 'Chengannur', 'district': 'Alappuzha'}).json()
    def count():
        return next(row for row in client.get('/api/admin/monitoring', headers=headers['admin']).json() if row['alert_id'] == alert['id'])['report_count']
    before = count()
    citizen_id = client.get('/api/users/me', headers=headers['citizen']).json()['id']
    with SessionLocal() as db:
        linked = Incident(user_id=citizen_id, reference='RQ-LINK-' + uuid4().hex[:8], message='A report requiring analysis to interpret its place spelling.', location='Chengannür', district='Alappuzha')
        linked.analysis = ReportAnalysis(result={'analysis_status': 'completed', 'extracted_location': 'Chengannür', 'district': 'Alappuzha', 'alert_match': {'status': 'MATCH', 'matched_alert_ids': [alert['id']], 'matched_alert_snapshots': [{'id': alert['id'], 'location': 'Chengannur', 'district': 'Alappuzha'}]}})
        unanalysed = Incident(user_id=citizen_id, reference='RQ-RAW-' + uuid4().hex[:8], message='Water is rising near Chengannur.', location='', district='ആലപ്പുഴ')
        db.add_all([linked, unanalysed])
        db.commit()
    assert count() == before + 2


def test_acceptance_preserves_bounded_operator_note_and_remains_idempotent(client, headers, incident):
    from backend.tests.test_extended import new_team
    team, operator = new_team(client, headers['admin'], 'rescue')
    ident = incident['id']
    assert client.post(f'/api/incidents/{ident}/review', headers=headers['admin'], json={'verified': True}).status_code == 200
    assigned = client.post('/api/teams/assign', headers=headers['admin'], json={'incident_id': ident, 'team_id': team['id']}).json()
    path = f'/api/teams/assignments/{assigned["assignment"]["id"]}/accept'
    assert client.post(path, headers=operator, json={'note': 'x' * 2001}).status_code == 422
    note = 'Team accepted; two personnel and a boat are ready.'
    accepted = client.post(path, headers=operator, json={'note': note})
    assert accepted.status_code == 200, accepted.text
    events = [event for event in accepted.json()['history'] if event['status'] == 'task_accepted']
    assert len(events) == 1 and events[0]['note'] == note
    repeated = client.post(path, headers=operator, json={'note': 'A later retry must not replace the original acceptance note.'})
    events = [event for event in repeated.json()['history'] if event['status'] == 'task_accepted']
    assert len(events) == 1 and events[0]['note'] == note


def test_monitoring_does_not_reuse_analysis_links_after_alert_area_changes(client, headers, monkeypatch):
    from backend.database.connection import SessionLocal
    from backend.models.incident import Incident, ReportAnalysis
    alert = client.post('/api/alerts', headers=headers['admin'], json={'title': 'Monitoring edited alert ' + uuid4().hex[:8], 'message': 'Synthetic monitoring regression', 'location': 'Chengannur', 'district': 'Alappuzha'}).json()
    citizen_id = client.get('/api/users/me', headers=headers['citizen']).json()['id']
    captured = []
    async def analyze(**payload):
        captured.append(payload)
        return {'analysis_status': 'completed', 'severity': 'LOW', 'extracted_location': 'Chengannur', 'district': 'Alappuzha', 'alert_match': {'status': 'MATCH', 'matched_alert_ids': [alert['id']]}}
    monkeypatch.setattr('backend.ai.agent.analyze_report', analyze)
    response = client.post('/api/incidents', headers=headers['citizen'], json={'message': 'Water is rising in Chengannur.', 'location': 'Chengannur', 'district': 'Alappuzha'})
    assert response.status_code == 201, response.text
    assert response.json()['analysis']['alert_match']['matched_alert_snapshots'] == [{'id': alert['id'], 'location': 'Chengannur', 'district': 'Alappuzha'}]
    with SessionLocal() as db:
        linked = Incident(user_id=citizen_id, reference='RQ-EDIT-' + uuid4().hex[:8], message='Unknown alternate place spelling.', location='Chengannür', district='Alappuzha')
        linked.analysis = ReportAnalysis(result={**response.json()['analysis'], 'extracted_location': 'Chengannür'})
        db.add(linked)
        db.commit()
    edited = client.put(f'/api/alerts/{alert["id"]}', headers=headers['admin'], json={'location': 'Cherthala'})
    assert edited.status_code == 200, edited.text
    monitoring = client.get('/api/admin/monitoring', headers=headers['admin'])
    row = next(row for row in monitoring.json() if row['alert_id'] == alert['id'])
    # Other test fixtures can legitimately be in Cherthala. The edited alert
    # must count neither the known nor unknown spelling of the old area.
    with SessionLocal() as db:
        from backend.services.alert_service import report_matches_alert
        from backend.models.alert import Alert
        current_alert = db.get(Alert, alert['id'])
        assert not report_matches_alert(db.get(Incident, response.json()['id']), current_alert)
        assert not report_matches_alert(db.get(Incident, linked.id), current_alert)
    assert row['report_count'] >= 0
