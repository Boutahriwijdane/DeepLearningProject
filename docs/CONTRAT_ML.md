# Contrat d'intégration avec le service de ta binôme

L'application peut être développée sans attendre l'entraînement. Un seul adaptateur,
`backend/app/ml.py`, relie les deux parties. Aucun TensorFlow n'est nécessaire dans le backend métier.

## Requête attendue

`POST /analyze`, fichier JPEG ou PNG envoyé en `multipart/form-data`, champ nommé `file`.
Le service doit accepter une image originale et retourner un JSON dans les 90 secondes
pour ce premier MVP synchrone. Plus tard, un worker permettra un traitement asynchrone.

## Réponse attendue

```json
{
  "mode": "real",
  "model_version": "mobilenetv2-v1",
  "classification": "invoice",
  "confidence": 0.94,
  "quality": "acceptable",
  "warnings": [],
  "ocr_text": "Texte réellement reconnu…",
  "fields": {
    "supplier": "Exemple de fournisseur",
    "invoice_number": "F-001",
    "invoice_date": "2026-10-31",
    "currency": "MAD",
    "subtotal": "100.00",
    "tax": "20.00",
    "total": "120.00"
  }
}
```

Les valeurs ci-dessus sont un exemple de contrat, pas des résultats du modèle.
Classification : `invoice`, `receipt`, `other` ou `null` si indéterminée.
Qualité : `acceptable`, `retake_required`, `unknown`.
Les champs non reconnus doivent valoir `null` ; les montants sont des chaînes décimales,
les dates au format ISO `YYYY-MM-DD`. La confiance vaut null si indisponible.
`mode=real` signifie que le service réel a répondu, pas que la qualité est garantie.
Si le contrôle qualité ou l'OCR ne sont pas implémentés, indiquer `unknown`, les champs
absents et un avertissement explicite.

Ordre des classes du notebook actuel : `invoice`, `other`, `receipt`.
La normalisation [-1, 1] est déjà incluse dans son modèle ; éviter de la doubler.
Conserver la résolution originale pour l'OCR, indépendamment du redimensionnement CNN.

## Activation

Dans `.env`, définir `ML_MODE=remote` et `ML_URL=http://host.docker.internal:8001/analyze`
si le service tourne sur Windows et le backend dans Docker Desktop.
Puis exécuter `docker compose up -d --force-recreate backend`.
En développement natif : définir `ML_URL=http://127.0.0.1:8001/analyze` dans le terminal backend.

La sortie brute est sauvegardée et chaque analyse laisse une trace.
Les champs corrigés à la main ne sont pas écrasés lors d'une nouvelle analyse.
