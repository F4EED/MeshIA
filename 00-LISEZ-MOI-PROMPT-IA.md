# MeshIA — procédure réutilisable (à donner à une IA)

Ce dossier contient tout ce qu'il faut pour recréer le socle MeshIA (étapes 5 et 6 du TODO) et continuer les tests.

## Comment s'en servir

1. Donne à l'IA **tous les fichiers .md de ce dossier** (00 à 04).
2. Colle-lui le prompt ci-dessous.
3. Elle te guidera pas à pas ; tu lui renvoies les sorties de terminal.

## Prompt à coller

> Tu es mon assistant technique pour le projet MeshIA. Lis les fichiers 00 à 04 que je te joins.
> Objectif : recréer sur mon ThinkCentre les fichiers `ingest.py`, `meshia.py` et les fiches Markdown, puis dérouler les tests de l'étape 6.
> Règles :
> - Une étape à la fois, dans l'ordre du fichier 04-TESTS. Attends ma sortie de terminal avant de passer à la suivante.
> - Je travaille en SSH sur Debian 12. Donne-moi les commandes prêtes à copier-coller.
> - Pour créer un fichier, donne-moi le contenu complet et dis-moi de l'ouvrir avec `nano` (pas de heredoc indenté, ça casse au collage).
> - Réponds en français, de façon concise.
> - Si une erreur apparaît, demande-moi la sortie complète avant de proposer un correctif.
> - L'API de la librairie `meshcore` varie selon les versions : si une méthode n'existe pas, vérifie avec `pip show meshcore` et `python -c "import meshcore; help(meshcore)"` avant de modifier le code.

## Contexte du projet

- **Projet** : MeshIA, un service qui répond à des questions envoyées en message privé sur un réseau mesh **MeshCore**. Les réponses viennent de fiches Markdown indexées dans SQLite (FTS5). Un LLM local (Ollama) est prévu plus tard, en option (étape 7).
- **Réseau** : mesh français, radio EU_868 (869.618 MHz, BW 62.5, SF8, CR8). Exercice terrain prévu plus tard avec le réseau Gaulix.
- **Machine** : ThinkCentre (Celeron G1840T, 16 Go DDR3), Debian 12 minimale, accès SSH.
- **Utilisateur** : `meshia` (droits sudo, groupe `dialout`).
- **Dossier de travail** : `/opt/meshia` (propriétaire `meshia`), avec :
  - `.venv/` : environnement virtuel Python, contient `meshcore` et `pyserial`.
  - `fiches/` : fiches Markdown.
  - `meshia.db` : base SQLite générée par `ingest.py`.
- **Nœud radio** : Seeed Studio XIAO ESP32-S3 avec module Wio-SX1262, firmware **Companion Radio USB**, nom du nœud `FR42-Meshia`, port série `/dev/ttyACM0`.

## État d'avancement (au moment de la rédaction)

- Étapes 1 à 4 du TODO : terminées (Debian, sudo, config de base, nœud MeshCore prêt).
- Étape 5 : `/opt/meshia/fiches`, venv, `pip install meshcore` faits. La connexion série et l'envoi/réception de messages ont été validés avec un script de test.
- **Reste à faire** : créer `ingest.py` et `meshia.py` (fichiers 01 et 02), créer les fiches (fichier 03), puis dérouler les tests (fichier 04). Ensuite : étape 7 (LLM) et étape 8 (systemd).

## Pièges connus (à rappeler à l'IA)

1. **Nœud qui ne répond plus après des ouvertures répétées du port série.** Les cartes ESP32-S3 à USB natif peuvent se bloquer quand on ouvre et ferme le port plusieurs fois de suite (les lignes DTR/RTS font redémarrer ou bloquent la carte). Symptôme : `MeshCore.create_serial(...)` renvoie `None` avec les logs « No response from meshcore node ». **Remède** : débrancher l'USB, attendre 5 secondes, rebrancher, attendre 5 secondes, puis lancer directement le script voulu. Avant chaque test, il faut aussi s'assurer qu'aucun autre script ne tient le port (`fuser -v /dev/ttyACM0`).
2. **Heredoc et indentation** : une commande `cat > fichier << 'EOF'` collée avec de l'indentation ne se termine jamais (le prompt affiche `>`). Solution : Ctrl+C, puis utiliser `nano`.
3. **Mauvais firmware** : seul **Companion Radio USB** fonctionne avec la librairie. Room Server, Repeater et Companion BLE ne répondent pas sur le port série.
4. **`dmesg` demande `sudo`** sur Debian 12.
5. **Limite de payload MeshCore** : environ 130 à 150 octets par message. Les réponses sont donc découpées (voir fichier 02).

## Fichiers de ce dossier

| Fichier | Contenu |
|---|---|
| `00-LISEZ-MOI-PROMPT-IA.md` | ce fichier : prompt, contexte, pièges |
| `01-ingest.py.md` | spécification et code de `ingest.py` |
| `02-meshia.py.md` | spécification et code de `meshia.py` |
| `03-fiches.md` | format des fiches et exemples à valider |
| `04-TESTS.md` | procédure de tests de l'étape 6, critères et dépannage |
