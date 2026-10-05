def test_inactive_campaigns_remain_admin_manageable(client, headers):
    body = {'title': 'Inactive demonstration campaign', 'description': 'A paused campaign used for a visibility regression test.', 'active': False, 'target_amount': 5000}
    response = client.post('/api/donations/campaigns', headers=headers['admin'], json=body)
    assert response.status_code == 201
    campaign_id = response.json()['id']
    assert campaign_id not in [row['id'] for row in client.get('/api/donations/campaigns').json()]
    assert campaign_id in [row['id'] for row in client.get('/api/admin/campaigns', headers=headers['admin']).json()]
    assert client.get('/api/admin/campaigns', headers=headers['citizen']).status_code == 403
    assert client.put(f'/api/donations/campaigns/{campaign_id}', headers=headers['admin'], json={**body, 'active': True}).status_code == 200
    assert campaign_id in [row['id'] for row in client.get('/api/donations/campaigns').json()]


def test_expired_alerts_and_draft_news_are_admin_only(client, headers):
    alert = client.post('/api/alerts', headers=headers['admin'], json={'title': 'Expired demo flood alert', 'message': 'A synthetic expired alert for a visibility test.', 'location': 'Aluva', 'district': 'Ernakulam', 'active': False}).json()
    assert alert['id'] not in [row['id'] for row in client.get('/api/alerts').json()]
    assert alert['id'] in [row['id'] for row in client.get('/api/admin/alerts', headers=headers['admin']).json()]
    assert client.get('/api/admin/alerts', headers=headers['citizen']).status_code == 403
    draft = client.post('/api/news', headers=headers['admin'], json={'title': 'Draft demo update', 'content': 'A synthetic unpublished community update.', 'published': False}).json()
    assert draft['id'] not in [row['id'] for row in client.get('/api/news').json()]
    assert draft['id'] in [row['id'] for row in client.get('/api/admin/news', headers=headers['admin']).json()]
    assert client.get('/api/admin/news', headers=headers['citizen']).status_code == 403
