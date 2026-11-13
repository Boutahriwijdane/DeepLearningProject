import os
import httpx
from .schemas import MLResult

def analyze(data: bytes, filename: str, content_type: str) -> MLResult:
    mode = os.getenv('ML_MODE', 'demo')
    if mode == 'demo':
        # Aucun résultat métier inventé : le formulaire peut être saisi à la main.
        return MLResult(mode='demo', model_version='not-connected', classification=None,
            quality='unknown', warnings=['Mode démonstration : modèle et OCR non connectés. Saisir les champs manuellement.'])
    if mode != 'remote':
        raise RuntimeError('ML_MODE doit être demo ou remote')
    url = os.getenv('ML_URL')
    if not url:
        raise RuntimeError('ML_URL manquant')
    with httpx.Client(timeout=90) as client:
        response = client.post(url, files={'file': (filename, data, content_type)})
        response.raise_for_status()
        result = MLResult.model_validate(response.json())
        if result.mode != 'real':
            raise ValueError('Le service distant doit indiquer mode=real')
        return result
