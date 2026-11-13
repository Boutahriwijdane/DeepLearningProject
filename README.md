# FactureFlow — première base de l'application

React + TypeScript, API FastAPI, PostgreSQL et stockage MinIO.
L'entraînement reste indépendant : le futur modèle se connecte via un service HTTP.

## Ce qui est livré

- Import JPEG/PNG (10 Mo max), contrôle du format réel, détection de doublons SHA-256.
- Liste paginée, recherche, filtre de statut, consultation de l'image originale.
- Analyse en mode démo, ou appel configurable d'un service ML réel.
- Correction des champs, vérification HT + TVA = TTC, validation manuelle.
- Historique persistant des actions et des anciennes/nouvelles valeurs corrigées.
- PostgreSQL pour les données, MinIO pour les images dans Docker Compose.

Le mode démo ne prédit aucune classe et n'invente aucun champ. Les données peuvent être
saisies à la main pour tester le parcours complet. La validation démo reste identifiée
comme telle dans les données et l'interface.

## Démarrage conseillé sous Windows

1. Ouvrir Docker Desktop et attendre que son moteur soit démarré.
2. Ouvrir un terminal PowerShell dans ce dossier (celui qui contient `compose.yaml`).
3. Exécuter :

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Ne pas écraser un `.env` déjà configuré.

- Application : http://localhost:8080
- Documentation interactive de l'API : http://localhost:8000/docs
- Console MinIO : http://localhost:9001
- PostgreSQL : localhost:55432, base `invoices`, utilisateur `invoice`, mot de passe `invoice_local`
- MinIO local : `invoice_storage` / `invoice_storage_local`

Les valeurs ci-dessus sont réservées au développement local. Les ports sont liés à 127.0.0.1.
Les données restent dans les volumes Docker après `docker compose down`.
Ne pas utiliser `down -v` si tu veux conserver les données.
Consulter les erreurs avec `docker compose logs backend`.

## Développement avec rechargement automatique

Démarrer uniquement PostgreSQL :

```powershell
docker compose up -d db
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DATABASE_URL = 'postgresql+psycopg://invoice:invoice_local@localhost:55432/invoices'
$env:ML_MODE = 'demo'
$env:STORAGE_MODE = 'local'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Dans un second terminal :

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Ouvrir l'adresse affichée par Vite (habituellement http://localhost:5173).
Le proxy Vite transmet `/api` au backend sur le port 8000.
En mode natif les images vont dans `backend/uploads/`; en Compose elles vont dans MinIO.
Pour un PostgreSQL déjà installé, adapter `DATABASE_URL` et créer la base au préalable.
La création initiale des tables est automatique ; les évolutions de schéma nécessiteront
des migrations Alembic avant de travailler sur des données à conserver.

## Organisation

```text
backend/app/main.py        Routes et règles du parcours documentaire
backend/app/models.py      Tables PostgreSQL via SQLAlchemy
backend/app/schemas.py     Validation des champs et contrat de réponse ML
backend/app/ml.py          Mode démo et adaptateur HTTP vers le service ML
backend/app/storage.py     Stockage local ou MinIO/S3
backend/tests/             Tests métier isolés
frontend/src/main.tsx      Écrans et appels API
frontend/src/style.css     Interface responsive en français
docs/CONTRAT_ML.md         Contrat à partager avec la binôme
compose.yaml              PostgreSQL + MinIO + backend + frontend
```

## Vérifications

```powershell
# Depuis backend, avec les dépendances installées
.\.venv\Scripts\python.exe -m pytest -q
# Depuis frontend
npm.cmd run build
```

Les tests backend utilisent une base SQLite temporaire pour isoler le parcours métier.
Ils ne remplacent pas une vérification d'intégration PostgreSQL/MinIO.

## Étapes suivantes

1. Lancer l'application et tester une vraie image, remplir puis valider ses champs.
2. Faire valider le contrat ML avec la binôme, puis connecter son service.
3. Ajouter authentification et permissions avant tout usage partagé.
4. Ajouter migrations Alembic, tests d'intégration PostgreSQL/MinIO, puis worker durable.
5. Ajouter le PDF multipage et enrichir les règles métier selon le périmètre demandé.

## Limites de cette première version

Application locale mono-utilisateur, sans authentification. Pas de PDF, pas de worker,
pas de contrôle qualité appris ni d'OCR embarqué. L'analyse ML est synchrone et peut
prendre jusqu'à 90 secondes ; le verrou PostgreSQL empêche les modifications concurrentes
sur le même document durant cet appel. Les fichiers sont conservés à l'identique.
Les montants négatifs/avoirs et plusieurs taux de TVA ne sont pas couverts par le formulaire MVP.
Les doublons sont détectés avant insertion ; une contrainte transactionnelle dédiée reste
à ajouter pour le cas de deux imports strictement simultanés.

Références : [FastAPI](https://fastapi.tiangolo.com/tutorial/request-files/),
[SQLAlchemy/PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html),
[Vite](https://vite.dev/guide/).

## Correctif Docker du 5 novembre 2026

Image MinIO remplacée par la distribution Coollabs fixée par digest. Contrôle de disponibilité : mc ready local. PostgreSQL est accessible sur localhost:55432 ; le backend utilise db:5432 dans Docker. Frontend, API, PostgreSQL et lecture/écriture MinIO vérifiés. Aucun besoin de recréer .env.
