from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_search_requires_valid_payload():
    response = client.post(
        '/api/search-buyers',
        json={
            'product_category': 'Home Decor',
            'product_description': 'Short',
            'buyer_type': 'Interior Designers',
            'location': 'New York, NY',
            'country': 'United States',
            'limit': 20,
        },
    )
    assert response.status_code == 422


def test_search_provider_not_configured():
    response = client.post(
        '/api/search-buyers',
        json={
            'product_category': 'Home Decor',
            'product_description': 'Handmade decorative wall art suitable for modern residential interiors.',
            'buyer_type': 'Interior Designers',
            'location': 'New York, NY',
            'country': 'United States',
            'limit': 20,
        },
    )
    assert response.status_code == 503
    assert 'not configured' in response.json()['detail'].lower()
