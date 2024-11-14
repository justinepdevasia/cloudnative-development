import pytest
from app import app
import io
import os
from unittest.mock import patch, MagicMock
import uuid

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['FLASK_SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
    with app.test_client() as client:
        yield client

@pytest.fixture
def test_email():
    return f"test_{uuid.uuid4().hex[:8]}@example.com"

@pytest.fixture
def authenticated_client(client, test_email):
    with client.session_transaction() as session:
        session['user'] = test_email
        session['user_hash'] = f"testhash_{uuid.uuid4().hex[:8]}"
    return client

def test_index_redirect_if_not_logged_in(client):
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.location

def test_login_success(client, test_email):
    with patch('app.auth') as mock_auth:
        mock_auth.sign_in_with_email_and_password.return_value = {'localId': 'testid'}
        response = client.post('/login', data={
            'email': test_email,
            'password': 'testpass123'
        })
        assert response.status_code == 302
        assert '/' in response.location

def test_register_success(client, test_email):
    with patch('app.auth') as mock_auth:
        mock_auth.create_user_with_email_and_password.return_value = {'localId': 'testid'}
        response = client.post('/register', data={
            'email': test_email,
            'password': 'testpass123'
        })
        assert response.status_code == 302

def test_upload_invalid_file(authenticated_client):
    data = {
        'file': (io.BytesIO(b'test content'), 'test.txt', 'text/plain')
    }
    response = authenticated_client.post('/', data=data, content_type='multipart/form-data')
    assert response.status_code == 400

def test_logout(authenticated_client):
    response = authenticated_client.get('/logout')
    with authenticated_client.session_transaction() as session:
        assert 'user' not in session
    assert response.status_code == 302