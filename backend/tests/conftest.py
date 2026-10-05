import os
from pathlib import Path
from uuid import uuid4

import pytest

Path('output').mkdir(exist_ok=True)
os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', f'sqlite:///./output/test-{uuid4().hex}.db')
os.environ['AI_ENABLED'] = 'false'
os.environ['DEMO_MODE'] = 'true'
os.environ['UPLOAD_DIR'] = f'output/test-uploads-{uuid4().hex}'


@pytest.fixture(scope='session')
def client():
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as session:
        yield session


@pytest.fixture
def sessions(client):
    result = {}
    for name in ['citizen', 'admin', 'rescue', 'investigation', 'relief', 'shelter']:
        response = client.post('/api/auth/login', json={'email': f'{name}@resq.local', 'password': 'ResqDemo!2026'})
        assert response.status_code == 200, response.text
        result[name] = response.json()
    return result


def auth(session):
    return {'Authorization': f'Bearer {session["access_token"]}'}


@pytest.fixture
def headers(sessions):
    return {name: auth(session) for name, session in sessions.items()}


@pytest.fixture
def incident(client, headers):
    response = client.post('/api/incidents', headers=headers['citizen'], json={
        'message': 'Two children are trapped by flood water in Chengannur. Please send rescue.',
        'location': 'Chengannur', 'district': 'Alappuzha', 'people_affected': 4,
        'help_required': ['rescue', 'water'], 'latitude': 9.318, 'longitude': 76.615,
    })
    assert response.status_code in (200, 201), response.text
    return response.json()
