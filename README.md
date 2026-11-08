# MeshIA

Service de réponses **privées MeshCore** : une question envoyée en message privé au nœud `FR42-Meshia` est rapprochée de fiches Markdown indexées dans **SQLite FTS5**. Un LLM local (**Ollama**) est prévu plus tard, en option.

Dépôt : [github.com/F4EED/MeshIA](https://github.com/F4EED/MeshIA) — **public**, licence [MIT](LICENSE).

## Architecture

```
[téléphone / autre nœud]
        │  message privé MeshCore (radio EU_868)
        ▼
[nœud Companion USB  FR42-Meshia  /dev/ttyACM0]
        │  série USB
        ▼
[ThinkCentre  /opt/meshia]
   meshia.py  ──►  meshia.db (FTS5)  ◄──  ingest.py  ◄──  fiches/*.md
```

- **Nœud** : Seeed XIAO ESP32-S3 + Wio-SX1262, firmware Companion Radio USB. Il transporte uniquement les messages privés.
- **ThinkCentre** : exécute le service Python. `ingest.py` lit les fiches et reconstruit la base. `meshia.py` écoute le port série, cherche la meilleure fiche et répond, découpé en messages courts.
- **Fiches** : 36 fichiers Markdown dans `fiches/` (5 exemples + extraits du wiki [wiki-resilience-pi](https://github.com/brunodesannicolas/wiki-resilience-pi)). Titre = mot-clé tapé par l’utilisateur ; l’essentiel tient dans les ~120 premiers caractères.

## Matériel et machine

| Élément | Valeur constatée |
|---|---|
| Machine | ThinkCentre, Celeron G1840T, 16 Go DDR3 |
| OS | **Debian 13** (bannière OpenSSH 10.0p2 Debian-7+deb13u4). Les specs initiales parlaient de Debian 12. |
| Accès | `meshia@192.168.1.57` (utilisateur `meshia`, sudo, groupe `dialout`) |
| Dossier | `/opt/meshia` |
| Nœud | `FR42-Meshia` sur `/dev/ttyACM0` |
| Radio | EU_868 (869.618 MHz, BW 62.5, SF8, CR8) ; exercice terrain Gaulix plus tard |

Ce cloud n’atteint pas le LAN : le relais passe par la machine GMC-Poste-maitre.

## État d’avancement

- **Étapes 1 à 5** : faites (Debian 13, sudo, nœud MeshCore, venv, paquet `meshcore`).
- **Étape 6** : faite. `ingest.py`, `meshia.py` et **36 fiches** sont en place. `meshia.py` répond en message privé MeshCore (`MESHIA_LLM=0`).
- **Reste** : étape 8 (service systemd 24/7). Étape 7 (LLM Ollama) optionnelle, **pas encore branchée**.

## Prérequis

- Python 3 du système Debian, `sqlite3` CLI (`sudo apt install sqlite3` si absent), FTS5 (inclus dans le SQLite de Debian).
- Environnement virtuel `/opt/meshia/.venv` avec `meshcore` et `pyserial`.
- Compte `meshia` dans le groupe `dialout`, nœud Companion USB branché sur `/dev/ttyACM0`.
- Un **autre** nœud (téléphone / appli companion) pour poser les questions en privé.

L’API `meshcore` varie selon les versions : en cas d’erreur d’appel, `pip show meshcore` puis `python -c "import meshcore; help(meshcore)"` avant de changer le code (specs 01–02).

## Structure des dossiers

Sur le ThinkCentre, sous `/opt/meshia` :

```
/opt/meshia/
  .venv/          # Python : meshcore, pyserial
  fiches/         # 36 fichiers .md
  ingest.py
  meshia.py
  meshia.db       # généré par ingest.py
```

Même arborescence (sans `.venv` ni `meshia.db`) dans ce dépôt.

## Variables d’environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `MESHIA_SERIAL` | `/dev/ttyACM0` | port série du nœud |
| `MESHIA_DB` | `/opt/meshia/meshia.db` | base SQLite FTS5 |
| `MESHIA_LLM` | `0` | `1` pour le LLM (étape 7, **pas encore branché**) |
| `MESHIA_MAXLEN` | `130` | taille max d’un message, en octets UTF-8 |
| `MESHIA_MAXPARTS` | `3` | nombre max de messages par réponse |
| `MESHIA_PAUSE` | `4` | secondes entre deux parties |

## Indexer et lancer

Specs : [01](01-ingest.py.md), [02](02-meshia.py.md), [03](03-fiches.md), tests : [04](04-TESTS.md). Sur le ThinkCentre, créer ou coller un fichier avec `nano` (pas un heredoc indenté).

Activer le venv, puis indexer (à relancer après chaque modification de fiche) :

```bash
cd /opt/meshia && source .venv/bin/activate
python ingest.py fiches
sqlite3 meshia.db "SELECT titre FROM fiches"
```

Sortie attendue : `36 fiches indexées`. Vérifier FTS5 sans le mesh, par exemple `MATCH 'brulure*'` (les accents sont ignorés).

Avant de lancer le service : aucun autre processus sur le port (`fuser -v /dev/ttyACM0`), USB débranché 5 s puis rebranché 5 s, `ls /dev/ttyACM*`. Un seul script, une seule ouverture.

```bash
MESHIA_LLM=0 python meshia.py
```

Log attendu : `MeshIA prête sur /dev/ttyACM0 (LLM=False)`. Ctrl+C arrête le processus.

Depuis un **autre** nœud, message privé à `FR42-Meshia` : `aide` (liste des sujets), une question libre (meilleure fiche), `zzzz` (« Rien trouvé. Sujets : … »). Si `FR42-Meshia` n’apparaît pas, envoyer un advert de chaque côté.

## Pièges connus

1. **Port série ESP32-S3** : ouvertures répétées → nœud muet, `create_serial` renvoie `None` (« No response from meshcore node »). Remède : débrancher 5 s, rebrancher 5 s, un seul script, `fuser -v /dev/ttyACM0` avant.
2. **Heredoc indenté** : `cat > fichier << 'EOF'` collé avec de l’indentation ne se termine jamais (prompt `>`). Ctrl+C, puis `nano`.
3. **Firmware** : seul **Companion Radio USB** parle sur le série. Room Server, Repeater et Companion BLE ne répondent pas.
4. **`dmesg`** exige `sudo` sur Debian.
5. **Payload MeshCore** ~130–150 octets : réponses découpées (`MESHIA_MAXLEN` / `MESHIA_MAXPARTS` / `MESHIA_PAUSE`). Si un message est refusé, baisser `MESHIA_MAXLEN` (ex. 110) ; si les parties se perdent, augmenter `MESHIA_PAUSE` (ex. 6).

## Documentation

Specs à lire plutôt que recopier :

- [Prompt, règles et pièges](00-LISEZ-MOI-PROMPT-IA.md)
- [ingest.py](01-ingest.py.md)
- [meshia.py](02-meshia.py.md)
- [Fiches Markdown](03-fiches.md)
- [Tests étape 6](04-TESTS.md)
