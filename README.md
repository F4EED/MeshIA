# MeshIA

**Version du document :** 1.7 — 8 novembre 2026 (Europe/Paris)

À chaque future mise à jour de ce README, incrémenter ce numéro.

Service de réponses **privées MeshCore** : une question envoyée en message privé au nœud `FR42-Meshia` est rapprochée de fiches Markdown indexées dans **SQLite FTS5** (RAG lexical). Avec `MESHIA_LLM=1`, un LLM local **Ollama** (`qwen2.5:0.5b`) reformule la fiche trouvée ; si Ollama est down, la fiche brute est renvoyée. Un **portail web LAN** (Apache → Flask) permet de saisir/importer des fiches et de tester la même recherche, sans passer par la radio. Les embeddings viendront plus tard. Pas d’HTTPS ni d’ouverture Internet pour l’instant.

Dépôt : [github.com/F4EED/MeshIA](https://github.com/F4EED/MeshIA) — **public**, licence [MIT](LICENSE). Racine locale : `C:\Apps\meshia`.

## Licence

[MIT](LICENSE) — Copyright (c) 2026 F4EED.

## Cloner

```bash
git clone https://github.com/F4EED/MeshIA.git
```

Copie de travail Windows : `C:\Apps\meshia`. Sur le ThinkCentre, le service tourne dans `/opt/meshia` (on y déploie `ingest.py`, `meshia.py`, `fiches/` et `meshia.service` ; ne pas versionner `.venv`, `meshia.db` ni de secrets).

## Architecture

```
[navigateur LAN]                  [téléphone / autre nœud]
        │                                  │  message privé MeshCore
        ▼                                  ▼
[Apache :80 /meshia]              [nœud Companion USB  FR42-Meshia]
        │ ProxyPass                        │  /dev/ttyACM0
        ▼                                  ▼
[meshia-web 127.0.0.1:8765]       [meshia.py]
        │                                  │
        └────────►  meshia.db (FTS5)  ◄────┘
                        ▲
                        │
              ingest.py  ◄──  fiches/*.md
                        │
                        └──  Ollama qwen2.5:0.5b  (radio seulement)
```

- **Nœud** : Seeed XIAO ESP32-S3 + Wio-SX1262, firmware Companion Radio USB. Il transporte uniquement les messages privés.
- **ThinkCentre** : `ingest.py` lit les fiches et reconstruit la base ; `meshia.py` écoute le port série, cherche la meilleure fiche FTS5, reformule éventuellement via Ollama, et répond en messages courts.
- **Portail web** : Flask dans le venv, `meshia-web.service`, Apache `ProxyPass /meshia` → `127.0.0.1:8765`. Auth locale, saisie/import de fiches, recherche FTS5 (texte brut, sans Ollama).
- **Fiches** : 47 fichiers Markdown dans `fiches/` (exemples + extraits du wiki). Titre = mot-clé tapé par l’utilisateur ; l’essentiel tient dans les ~120 premiers caractères.

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
- **Étape 6** : faite. `ingest.py`, `meshia.py` et **47 fiches** indexées. Réponses en message privé MeshCore.
- **Étape 8** : faite. Unité systemd `meshia.service` **enabled** + **active**.
- **Étape 7** : faite. Ollama local `qwen2.5:0.5b`, `MESHIA_LLM=1` (défini dans l’unité systemd) reformule la fiche FTS5, avec fallback texte brut si Ollama est down. RAG = FTS5 ; embeddings plus tard.
- **Portail web** : fait. `http://192.168.1.57/meshia` (LAN, login/mot de passe). Unité `meshia-web.service` distincte : ne touche ni `meshia.service`, ni `/dev/ttyACM0`, ni Ollama.

## Prérequis

- Python 3 du système Debian, `sqlite3` CLI (`sudo apt install sqlite3` si absent), FTS5 (inclus dans le SQLite de Debian).
- Environnement virtuel `/opt/meshia/.venv` avec `meshcore` et `pyserial`.
- Ollama (systemd `ollama.service`) et modèle `qwen2.5:0.5b` pour `MESHIA_LLM=1`.
- Compte `meshia` dans le groupe `dialout`, nœud Companion USB branché sur `/dev/ttyACM0`.
- Un **autre** nœud (téléphone / appli companion) pour poser les questions en privé.
- Portail web : `flask`, `waitress`, `python-docx` dans le venv ; paquets Debian `poppler-utils` et `catdoc` (PDF / .doc) ; Apache `proxy` + `proxy_http`.

L’API `meshcore` varie selon les versions : en cas d’erreur d’appel, `pip show meshcore` puis `python -c "import meshcore; help(meshcore)"` avant de changer le code (specs 01–02).

## Structure des dossiers

Sur le ThinkCentre, sous `/opt/meshia` :

```
/opt/meshia/
  .venv/          # Python : meshcore, pyserial, flask, waitress, python-docx (non versionné)
  fiches/         # 47 fichiers .md
  ingest.py
  meshia.py
  meshia.db       # généré par ingest.py (non versionné)
  web/            # portail Flask, conf Apache, unité meshia-web
    users.json    # hashes de mots de passe, chmod 600, hors git
    secret.key    # secret de session, chmod 600, hors git
```

Unités systemd : `/etc/systemd/system/meshia.service` (radio) et `meshia-web.service` (portail). Copies dans ce dépôt : `meshia.service`, `web/meshia-web.service`, `web/apache-meshia.conf`. Même arborescence applicative (sans `.venv`, `meshia.db` ni secrets) dans `C:\Apps\meshia` et sur GitHub.

## Fiches et sources wiki

**47 fiches** indexées. Origine :

- 5 exemples de départ (`brulure`, `saignement`, `eau`, `radio`, `urgence`) ;
- extraits du wiki [wiki-resilience-pi / wiki_pages](https://github.com/brunodesannicolas/wiki-resilience-pi/tree/main/wiki_pages) (**32 pages**, y compris les `start.txt`).

Dernier parcours wiki : 10 nouveaux titres — Energie, Nourriture, Secours, Securite, Purification, Culture, PLS, Survie, Tempete, Frequences — plus **Communication**. Les autres pages ont été fusionnées dans des fiches existantes (synonymes) ou laissées de côté (hors sujet, trop longues, incomplètes).

## Variables d’environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `MESHIA_SERIAL` | `/dev/ttyACM0` | port série du nœud |
| `MESHIA_DB` | `/opt/meshia/meshia.db` | base SQLite FTS5 |
| `MESHIA_LLM` | `0` | `1` pour reformuler la fiche via Ollama (l’unité systemd force `1`) |
| `MESHIA_MODEL` | `qwen2.5:0.5b` | modèle Ollama |
| `MESHIA_OLLAMA` | `http://127.0.0.1:11434/api/generate` | API generate |
| `MESHIA_LLM_TIMEOUT` | `45` | secondes avant fallback fiche brute |
| `MESHIA_MAXLEN` | `130` | taille max d’un message, en octets UTF-8 |
| `MESHIA_MAXPARTS` | `3` | nombre max de messages par réponse |
| `MESHIA_PAUSE` | `4` | secondes entre deux parties |
| `MESHIA_WEB_BIND` | `127.0.0.1` | écoute du portail Flask (localhost seulement) |
| `MESHIA_WEB_PORT` | `8765` | port local proxifié par Apache `/meshia` |
| `MESHIA_WEB_USERS` | `/opt/meshia/web/users.json` | identifiants hashés (chmod 600, hors git) |
| `MESHIA_WEB_SECRET` | `/opt/meshia/web/secret.key` | secret de session Flask (chmod 600, hors git) |

## Indexer et lancer

Specs : [01](01-ingest.py.md), [02](02-meshia.py.md), [03](03-fiches.md), tests : [04](04-TESTS.md). Sur le ThinkCentre, créer ou coller un fichier avec `nano` (pas un heredoc indenté).

Activer le venv, puis indexer (à relancer après chaque modification de fiche) :

```bash
cd /opt/meshia && source .venv/bin/activate
python ingest.py fiches
sqlite3 meshia.db "SELECT titre FROM fiches"
```

Sortie attendue : `47 fiches indexées`. Vérifier FTS5 sans le mesh, par exemple `MATCH 'brulure*'` (les accents sont ignorés).

Le service 24/7 est **systemd**. Un seul process sur `/dev/ttyACM0` : ne pas lancer `python meshia.py` à la main tant que l’unité tourne.

```bash
sudo systemctl status meshia
sudo journalctl -u meshia -n 50 --no-pager
```

Log attendu : `MeshIA prête sur /dev/ttyACM0 (LLM=True)` (unité systemd avec `MESHIA_LLM=1`). La recherche reste du FTS5 ; le LLM ne reformule que la fiche trouvée.

```bash
sudo systemctl stop meshia     # libère le port
sudo systemctl start meshia    # une seule ouverture
```

L’unité a `Restart=on-failure` et `StartLimitBurst=1` : pas de relance en rafale si le nœud USB meurt. Dans ce cas : `systemctl stop meshia`, débrancher l’USB 5 s, rebrancher 5 s, puis `start` une fois.

### Tests radio

Depuis un **autre** nœud, message privé à `FR42-Meshia` :

1. `aide` — liste des sujets.
2. Une question libre (ex. `brûlure`, `comment potabiliser l'eau`) — meilleure fiche, éventuellement reformulée.
3. `zzzz` — « Rien trouvé. Sujets : … ».

### Advert flood

Si `FR42-Meshia` n’apparaît pas : **un seul process série**. Arrêter systemd, envoyer un advert en flood, relancer.

```bash
sudo systemctl stop meshia
cd /opt/meshia && source .venv/bin/activate
```

Coller ce script avec `nano` (pas un heredoc indenté), l’exécuter, puis le supprimer :

```python
import asyncio
from meshcore import MeshCore

async def main():
    mc = await MeshCore.create_serial("/dev/ttyACM0")
    print(await mc.commands.send_advert(flood=True))
    await mc.disconnect()

asyncio.run(main())
```

```bash
sudo systemctl start meshia
```

Résultat attendu : événement `command_ok`. Relancer systemd **une seule fois**.

## Portail web (LAN)

URL : [http://192.168.1.57/meshia](http://192.168.1.57/meshia) — Apache sur le port 80, `ProxyPass` vers Flask `127.0.0.1:8765`. Pas d’HTTPS.

**Login** : compte local `meshia`. Le mot de passe n’est **pas** dans git : hashes dans `web/users.json` (`chmod 600`). Créer le premier compte :

```bash
cd /opt/meshia && source .venv/bin/activate
python web/init_users.py meshia    # mot de passe sur stdin, une ligne
```

**Saisir** une fiche (titre + texte) → `fiches/<titre-safe>.md` puis `python ingest.py fiches`.

**Importer** un fichier `txt`, `md`, `pdf`, `doc` ou `docx` : extraction du texte, même pipeline. Les `.doc` anciens sont en best-effort.

**URL** : [http://192.168.1.57/meshia/url](http://192.168.1.57/meshia/url) — coller une adresse http(s) (pas de `file://`). MeshIA affiche d’abord la **fiche proposée** (titre + texte). Rien n’est écrit tant qu’on n’a pas cliqué sur **Créer** (`fiches/*.md` + `ingest.py`). Timeout 15 s, max 1 Mo.

**Utilisateurs** (compte `meshia`) : [http://192.168.1.57/meshia/utilisateurs](http://192.168.1.57/meshia/utilisateurs) — lister, créer, changer un mot de passe, supprimer. Hashes uniquement, jamais les mots de passe en clair. Le compte `meshia` ne peut pas être supprimé.

**Recherche** : [http://192.168.1.57/meshia/recherche](http://192.168.1.57/meshia/recherche) — même FTS5 `meshia.db` et même logique que `meshia.py` (`MATCH`, accents ignorés, bm25, `aide` / « Rien trouvé »). La fiche (titre + texte brut, sans Ollama) s’affiche **sous le champ**, encadrée. Si FTS5 ne trouve rien : « Rien trouvé. Sujets : … » (jamais une page vide). Exemple : `?q=radio`.

Service web (ne pas confondre avec `meshia.service` radio) :

```bash
sudo systemctl status meshia-web
sudo journalctl -u meshia-web -n 50 --no-pager
```

Apache : copier `web/apache-meshia.conf` vers `/etc/apache2/conf-available/meshia.conf`, puis `a2enmod proxy proxy_http headers && a2enconf meshia && systemctl reload apache2`.

## Pièges connus

1. **Port série ESP32-S3** : ouvertures répétées → nœud muet, `create_serial` renvoie `None` (« No response from meshcore node »). Remède : débrancher 5 s, rebrancher 5 s, un seul script, `fuser -v /dev/ttyACM0` avant.
2. **Heredoc indenté** : `cat > fichier << 'EOF'` collé avec de l’indentation ne se termine jamais (prompt `>`). Ctrl+C, puis `nano`.
3. **Firmware** : seul **Companion Radio USB** parle sur le série. Room Server, Repeater et Companion BLE ne répondent pas.
4. **`dmesg`** exige `sudo` sur Debian.
5. **Payload MeshCore** ~130–150 octets : réponses découpées (`MESHIA_MAXLEN` / `MESHIA_MAXPARTS` / `MESHIA_PAUSE`). Si un message est refusé, baisser `MESHIA_MAXLEN` (ex. 110) ; si les parties se perdent, augmenter `MESHIA_PAUSE` (ex. 6).
6. **Secrets du portail** : `web/users.json` et `web/secret.key` hors git, `chmod 600`. Ne pas les coller dans le README.

## Documentation

Specs à lire plutôt que recopier :

- [Prompt, règles et pièges](00-LISEZ-MOI-PROMPT-IA.md)
- [ingest.py](01-ingest.py.md)
- [meshia.py](02-meshia.py.md)
- [Fiches Markdown](03-fiches.md)
- [Tests étape 6](04-TESTS.md)
