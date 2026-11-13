# Vérifications du 31 octobre 2026

- Frontend : vérification TypeScript et compilation Vite réussies.
- Backend : six tests métier réussis avec une base SQLite temporaire.
- PostgreSQL 16 : instance isolée créée sur le port local 55432 dans le dossier
  de travail ; tables créées par l'application, import d'une image fictive, analyse
  démo et consultation de l'original réussis via HTTP.
- Interface : consultation, saisie des champs et validation manuelle de cette
  image réussies avec persistance PostgreSQL et événements d'historique.
- Affichage : écran étroit et mise en page de bureau inspectés dans le navigateur.
- Docker Compose : configuration validée avec `docker compose config --quiet`.

Le moteur Docker n'étant pas disponible pendant la vérification, les images Docker,
le stockage MinIO et l'exécution complète sous Compose n'ont pas été testés.
Le stockage local a été testé. Aucun service ML réel n'était disponible.

La base temporaire et les serveurs de vérification ont été arrêtés après les essais.
Utiliser le README pour démarrer son propre environnement de développement.
