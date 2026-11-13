import hashlib
import io
import logging
import warnings
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import AuditEvent, Document, Invoice
from .schemas import InvoiceFields
from . import ml, storage

log = logging.getLogger(__name__)
MAX_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    storage.initialize()
    yield

app = FastAPI(title='FactureFlow API', version='0.1.0', lifespan=lifespan)

def event(db, document, action, details=None):
    db.add(AuditEvent(document_id=document.id, action=action, details=details or {}))

def get_document(db, document_id):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, 'Document introuvable')
    return document

def invoice_dict(invoice):
    if not invoice:
        return None
    return {key: str(value) if isinstance(value, Decimal) else value
        for key in InvoiceFields.model_fields for value in [getattr(invoice, key)]}

def serialize(db, document):
    return {key: getattr(document, key) for key in
        ('id', 'filename', 'status', 'classification', 'ml_result', 'error', 'created_at')} | {
        'fields': invoice_dict(db.get(Invoice, document.id))}

@app.get('/api/health')
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    import os
    return {'status': 'ok', 'ml_mode': os.getenv('ML_MODE', 'demo')}

@app.post('/api/documents', status_code=201)
def upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = file.file.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, 'Image vide ou supérieure à 10 Mo')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                fmt = image.format
                if fmt not in ('JPEG', 'PNG'):
                    raise HTTPException(415, 'Seules les images JPEG et PNG sont acceptées')
                image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning, SyntaxError, ValueError):
        raise HTTPException(415, 'Image illisible ou dimensions excessives')
    digest = hashlib.sha256(data).hexdigest()
    duplicate = db.scalar(select(Document).where(Document.sha256 == digest).limit(1))
    if duplicate:
        raise HTTPException(409, {'message': 'Ce document existe déjà', 'document_id': duplicate.id})
    document_id = str(uuid4())
    mime = 'image/jpeg' if fmt == 'JPEG' else 'image/png'
    key = document_id + ('.jpg' if fmt == 'JPEG' else '.png')
    storage.put(key, data, mime)
    document = Document(id=document_id, filename=Path(file.filename or 'image').name[:255],
        content_type=mime, storage_key=key, sha256=digest)
    try:
        db.add(document)
        db.add(Invoice(id=document_id))
        # Flush du document avant les objets qui le référencent.
        db.flush([document])
        event(db, document, 'uploaded')
        db.commit()
    except Exception:
        db.rollback()
        storage.remove(key)
        raise
    return serialize(db, document)

@app.get('/api/documents')
def listing(q: str = '', status: str = '', limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    statement = select(Document).order_by(Document.created_at.desc())
    if q:
        statement = statement.where(Document.filename.ilike(f'%{q}%'))
    if status:
        statement = statement.where(Document.status == status)
    return [serialize(db, d) for d in db.scalars(statement.offset(offset).limit(limit))]

@app.get('/api/documents/{document_id}')
def detail(document_id: str, db: Session = Depends(get_db)):
    return serialize(db, get_document(db, document_id))

@app.get('/api/documents/{document_id}/image')
def preview(document_id: str, db: Session = Depends(get_db)):
    document = get_document(db, document_id)
    return Response(storage.read(document.storage_key), media_type=document.content_type,
        headers={'X-Content-Type-Options': 'nosniff'})

@app.post('/api/documents/{document_id}/process')
def process(document_id: str, db: Session = Depends(get_db)):
    # Verrou sur la ligne pendant le traitement : deux requêtes concurrentes
    # ne peuvent pas traiter/corriger simultanément un même document sous PostgreSQL.
    document = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if not document:
        raise HTTPException(404, 'Document introuvable')
    if document.status == 'validated':
        raise HTTPException(409, 'Document validé : modification et retraitement désactivés')
    try:
        result = ml.analyze(storage.read(document.storage_key), document.filename, document.content_type)
    except Exception:
        log.exception('Échec ML pour %s', document_id)
        document.status = 'failed'
        document.error = 'Service ML indisponible ou réponse invalide. Réessayer ultérieurement.'
        event(db, document, 'processing_failed')
        db.commit()
        raise HTTPException(502, document.error)
    document.ml_result = result.model_dump(mode='json')
    document.classification = result.classification
    document.error = None
    document.status = ('demo' if result.mode == 'demo' else
        'retake_required' if result.quality == 'retake_required' else
        'out_of_scope' if result.classification == 'other' else 'manual_review')
    # Les résultats ML restent séparés des champs corrigés manuellement.
    invoice = db.get(Invoice, document_id)
    edited = db.scalar(select(AuditEvent.id).where(AuditEvent.document_id == document_id,
        AuditEvent.action == 'fields_updated').limit(1))
    if not edited and result.mode == 'real' and document.status == 'manual_review':
        for key, value in result.fields.model_dump(mode='json').items():
            setattr(invoice, key, value)
    event(db, document, 'processed', document.ml_result)
    db.commit()
    return serialize(db, document)

@app.patch('/api/documents/{document_id}/fields')
def update(document_id: str, fields: InvoiceFields, db: Session = Depends(get_db)):
    document = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if not document:
        raise HTTPException(404, 'Document introuvable')
    if document.status == 'validated':
        raise HTTPException(409, 'Document déjà validé')
    invoice = db.get(Invoice, document_id)
    before = invoice_dict(invoice)
    for key, value in fields.model_dump(mode='json').items():
        setattr(invoice, key, value)
    event(db, document, 'fields_updated', {'before': before, 'after': fields.model_dump(mode='json')})
    db.commit()
    return serialize(db, document)

@app.post('/api/documents/{document_id}/validate')
def validate(document_id: str, db: Session = Depends(get_db)):
    document = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if not document:
        raise HTTPException(404, 'Document introuvable')
    if document.status not in ('manual_review', 'demo'):
        raise HTTPException(409, 'Traiter le document et résoudre ses alertes avant validation')
    invoice = db.get(Invoice, document_id)
    if not all([invoice.supplier, invoice.invoice_number, invoice.invoice_date, invoice.total is not None]):
        raise HTTPException(422, 'Fournisseur, numéro, date et total sont obligatoires')
    if invoice.subtotal is not None and invoice.tax is not None:
        if abs(invoice.subtotal + invoice.tax - invoice.total) > Decimal('0.02'):
            raise HTTPException(422, 'Le montant HT + TVA ne correspond pas au TTC')
    document.status = 'validated'
    event(db, document, 'validated', {'demo': (document.ml_result or {}).get('mode') == 'demo'})
    db.commit()
    return serialize(db, document)

@app.get('/api/documents/{document_id}/events')
def events(document_id: str, db: Session = Depends(get_db)):
    get_document(db, document_id)
    return [{'id': e.id, 'action': e.action, 'details': e.details, 'created_at': e.created_at}
        for e in db.scalars(select(AuditEvent).where(AuditEvent.document_id == document_id)
            .order_by(AuditEvent.created_at))]
