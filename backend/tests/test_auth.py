import os

os.environ['APP_ENV'] = 'test'

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_signup_and_login_success():
    signup = client.post(
        '/api/auth/signup',
        json={
            'name': 'Test User',
            'email': 'test@example.com',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
        },
    )
    assert signup.status_code == 200
    payload = signup.json()
    assert payload['user']['email'] == 'test@example.com'
    assert 'token' in payload

    login = client.post(
        '/api/auth/login',
        json={
            'email': 'test@example.com',
            'password': 'StrongPassword123!',
        },
    )
    assert login.status_code == 200
    assert login.json()['user']['email'] == 'test@example.com'


def test_signup_rejects_duplicate_email():
    client.post(
        '/api/auth/signup',
        json={
            'name': 'Another User',
            'email': 'duplicate@example.com',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
        },
    )

    response = client.post(
        '/api/auth/signup',
        json={
            'name': 'Another User',
            'email': 'duplicate@example.com',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
        },
    )
    assert response.status_code == 409
