# Vérification et classement automatique des factures (CNN + OCR)

Projet de Deep Learning (5IIR-DDSI), réalisé par BELKHOU Zainab et BOUTAHRI Wijdane.

Le système classe un document (facture, ticket, autre), détecte les images de mauvaise qualité (floues, mal cadrées), puis extrait par OCR le fournisseur, la date et le total des factures. Il se compose de deux parties reliées par une API HTTP :

- **Service ML** (`ml_service/`) : deux classifieurs MobileNetV2 (transfert d'apprentissage) et Tesseract.
- **Application FactureFlow** (`backend/`, `frontend/`) : import, correction et validation des documents. Voir `README.md` pour son installation.

## Structure du dépôt

```
.
├── README.md                  application FactureFlow
├── README_ML.md               ce fichier
├── compose.yaml, .env.example
├── backend/  frontend/  docs/
├── ml_service/
│   ├── service.py             API FastAPI (POST /analyze)
│   ├── requirements.txt
│   └── models/                modèles .keras (non versionnés, voir plus bas)
├── notebooks/
│   ├── 01_data_and_training.ipynb   données, entraînement, évaluation, OCR
│   └── 02_service_colab.ipynb       service ML sur Colab (solution de secours)
└── report/
    └── fiche_exp.pdf          fiche expérimentale
```

## Résultats

| Tâche | Résultat |
|---|---|
| Classifieur de type (375 images de test) | exactitude 0,992 ; F1 macro 0,990 |
| Classifieur de qualité (300 images de test) | exactitude 0,947 ; AUC 0,9953 |
| OCR, date (96 factures annotées) | 87,5 % |
| OCR, total (84 factures annotées) | 82,1 % |
| OCR, fournisseur (73 factures annotées) | 57,5 % exact ; 71,2 % avec similarité ≥ 0,8 |
| Analyse complète d'une image (PC local, CPU) | environ 3 s |

Détails, matrices de confusion et courbes : `report/fiche_exp.pdf`.

Ces scores sont probablement surestimés : les données de FATURA sont générées à partir de gabarits (communs à l'entraînement et au test), les défauts de qualité sont synthétiques, et les règles d'extraction ont été ajustées sur ce jeu de données.

## Installation du service ML (Windows)

Prérequis :

1. **Python 3** (testé avec Python 3.13).
2. **Tesseract OCR**, avec les données de langue (`eng`, et `fra` si besoin). Chemin par défaut utilisé : `C:\Program Files\Tesseract-OCR\tesseract.exe`.
3. **Les deux modèles** `invoice_classifier.keras` et `quality_classifier.keras`, à placer dans `ml_service/models/` : [lien Drive à ajouter].

Installation :

```powershell
cd ml_service
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Lancement

Service ML (port 8001) :

```powershell
cd ml_service
$env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
$env:TESSDATA_PREFIX = 'C:\tessdata'   # seulement si Tesseract signale un fichier .traineddata introuvable
.\.venv\Scripts\python.exe service.py
```

Test rapide :

```powershell
curl.exe -sS -F "file=@C:\chemin\facture.png" http://localhost:8001/analyze
```

Application FactureFlow, dans le dossier racine : dans `.env`, définir

```
ML_MODE=remote
ML_URL=http://host.docker.internal:8001/analyze
```

puis `docker compose up -d --build`. L'application est disponible sur http://localhost:8080.

## Contrat de l'API

`POST /analyze`, image JPEG ou PNG envoyée en `multipart/form-data` (champ `file`). Réponse :

- `mode` (`real`), `model_version`
- `classification` : `invoice`, `receipt` ou `other`
- `confidence` : confiance de la classification
- `quality` : `acceptable` ou `retake_required`
- `warnings` : liste de messages
- `ocr_text` : texte reconnu
- `fields` : `supplier`, `invoice_number`, `invoice_date`, `subtotal`, `tax`, `total`

Seuls le fournisseur, la date et le total sont extraits. Les autres champs valent `null`. Spécification complète : `docs/CONTRAT_ML.md`.

## Données et licences

| Jeu de données | Usage | Licence |
|---|---|---|
| FATURA (Zenodo) | factures (1 000 images) et évaluation de l'OCR | à vérifier sur la page Zenodo |
| CORD (Naver Clova) | tickets (1 000 images) | CC BY 4.0 |
| RVL-CDIP (Hugging Face) | autres documents (500 images) | recherche uniquement |

Les jeux de données ne sont pas inclus dans le dépôt. Le notebook `01_data_and_training.ipynb` les télécharge.

## Limites

- Un seul modèle (MobileNetV2) : pas de comparaison avec VGG19 ou ResNet50.
- Données synthétiques ou génériques ; aucun test sur de vraies factures.
- Extraction des champs non prise en charge pour les tickets, et pour le numéro de facture, le montant hors taxes et la TVA.
- Pas de quantification ni d'optimisation de l'inférence.