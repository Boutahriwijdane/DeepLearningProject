import io
import os
import tempfile
from pathlib import Path

# Le stockage SQLite est réservé aux tests isolés. L'application utilise PostgreSQL.
TEMP = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(TEMP.name) / 'test.db')
os.environ['UPLOAD_DIR'] = str(Path(TEMP.name) / 'uploads')
os.environ['STORAGE_MODE'] = 'local'
os.environ['ML_MODE'] = 'demo'

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app.database import Base, engine

@pytest.fixture(scope='module', autouse=True)
def cleanup_database():
    yield
    engine.dispose()
    TEMP.cleanup()

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as client:
        yield client

def upload(client, color='white'):
    image = io.BytesIO()
    Image.new('RGB', (300, 400), color).save(image, format='PNG')
    return client.post('/api/documents', files={'file': ('facture.png', image.getvalue(), 'image/png')})

FIELDS = {'supplier': 'Fournisseur test', 'invoice_number': 'F-001',
    'invoice_date': '2026-10-31', 'currency': 'MAD', 'subtotal': '100.00', 'tax': '20.00', 'total': '120.00'}

def test_complete_manual_workflow(client):
    response = upload(client)
    assert response.status_code == 201, response.text
    document_id = response.json()['id']
    assert client.get(f'/api/documents/{document_id}/image').headers['content-type'] == 'image/png'
    result = client.post(f'/api/documents/{document_id}/process').json()
    assert result['status'] == 'demo'
    assert result['classification'] is None
    assert result['fields']['supplier'] is None
    assert client.patch(f'/api/documents/{document_id}/fields', json=FIELDS).status_code == 200
    response = client.post(f'/api/documents/{document_id}/validate')
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'validated'
    assert client.patch(f'/api/documents/{document_id}/fields', json=FIELDS).status_code == 409
    assert client.post(f'/api/documents/{document_id}/process').status_code == 409
    assert len(client.get(f'/api/documents/{document_id}/events').json()) == 4
    assert client.get('/api/documents?status=validated').json()[0]['fields']['total'] == '120.00'

def test_invalid_upload_and_duplicate(client):
    assert client.post('/api/documents', files={'file': ('evil.png', b'not an image', 'image/png')}).status_code == 415
    assert upload(client).status_code == 201
    assert upload(client).status_code == 409
    assert client.get('/api/documents/missing').status_code == 404

def test_validation_requires_fields_and_consistency(client):
    document_id = upload(client).json()['id']
    assert client.post(f'/api/documents/{document_id}/validate').status_code == 409
    client.post(f'/api/documents/{document_id}/process')
    assert client.post(f'/api/documents/{document_id}/validate').status_code == 422
    assert client.patch(f'/api/documents/{document_id}/fields', json=FIELDS | {'total': '-1'}).status_code == 422
    client.patch(f'/api/documents/{document_id}/fields', json=FIELDS | {'total': '150.00'})
    assert client.post(f'/api/documents/{document_id}/validate').status_code == 422

def test_remote_failure_is_persisted(client, monkeypatch):
    document_id = upload(client).json()['id']
    def fail(*args):
        raise RuntimeError('simulated remote failure')
    monkeypatch.setattr('app.ml.analyze', fail)
    assert client.post(f'/api/documents/{document_id}/process').status_code == 502
    assert client.get(f'/api/documents/{document_id}').json()['status'] == 'failed'

def test_reprocessing_preserves_human_corrections(client, monkeypatch):
    from app.schemas import MLResult, InvoiceFields
    document_id = upload(client).json()['id']
    client.patch(f'/api/documents/{document_id}/fields', json=FIELDS)
    monkeypatch.setattr('app.ml.analyze', lambda *args: MLResult(mode='real', model_version='test-1',
        classification='invoice', confidence=0.96, quality='acceptable',
        fields=InvoiceFields(supplier='Prédiction différente')))
    result = client.post(f'/api/documents/{document_id}/process').json()
    assert result['status'] == 'manual_review'
    assert result['fields']['supplier'] == 'Fournisseur test'
    assert result['ml_result']['fields']['supplier'] == 'Prédiction différente'

def test_bad_quality_cannot_be_validated(client, monkeypatch):
    from app.schemas import MLResult
    document_id = upload(client).json()['id']
    monkeypatch.setattr('app.ml.analyze', lambda *args: MLResult(mode='real', model_version='test-1',
        classification='invoice', quality='retake_required'))
    assert client.post(f'/api/documents/{document_id}/process').json()['status'] == 'retake_required'
    client.patch(f'/api/documents/{document_id}/fields', json=FIELDS)
    assert client.post(f'/api/documents/{document_id}/validate').status_code == 409
