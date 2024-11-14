import pytest
import requests

BASE_URL = "https://image-gallery-603299515919.us-central1.run.app"

def test_invalid_login():
    data = {
        'email': 'test@example.com',
        'password': 'wrongpassword'
    }
    response = requests.post(f"{BASE_URL}/login", data=data)
    assert response.status_code == 200
    assert b'Invalid credentials' in response.content

def test_register_page():
    response = requests.get(f"{BASE_URL}/register")
    assert response.status_code == 200
    assert b'Register' in response.content

def test_login_page():
    response = requests.get(f"{BASE_URL}/login")
    assert response.status_code == 200
    assert b'Login' in response.content