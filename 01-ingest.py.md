# 01 — `ingest.py` : indexer les fiches dans SQLite

## Rôle

Lit tous les fichiers `*.md` d'un dossier (par défaut `fiches/`) et construit une table SQLite **FTS5** dans `/opt/meshia/meshia.db`. À relancer à chaque modification des fiches : la table est recréée entièrement.

## Règles de conception

- Le titre de la fiche est la première ligne si elle commence par `#`, sinon le nom du fichier sans extension.
- Le contenu est le reste du fichier, sur une seule ligne (les retours à la ligne sont remplacés par des espaces).
- Tokenizer `unicode61 remove_diacritics 2` : « brulure » trouve « Brûlure ».
- Colonnes : `titre`, `contenu`, `fichier` (non indexée).
- Variable d'environnement : `MESHIA_DB` (chemin de la base, défaut `/opt/meshia/meshia.db`).
- Sortie attendue : `N fiches indexées`.

## Création du fichier

```bash
cd /opt/meshia && source .venv/bin/activate
nano ingest.py
```

Coller le code ci-dessous, puis Ctrl+O, Entrée, Ctrl+X.

## Code

```python
import os, pathlib, sqlite3, sys

DB = os.environ.get("MESHIA_DB", "/opt/meshia/meshia.db")
dossier = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "fiches")

con = sqlite3.connect(DB)
con.execute("DROP TABLE IF EXISTS fiches")
con.execute(
    "CREATE VIRTUAL TABLE fiches USING fts5("
    "titre, contenu, fichier UNINDEXED, "
    "tokenize='unicode61 remove_diacritics 2')"
)

n = 0
for f in sorted(dossier.glob("*.md")):
    lignes = f.read_text(encoding="utf-8").strip().splitlines()
    titre = f.stem
    if lignes and lignes[0].startswith("#"):
        titre = lignes[0].lstrip("# ").strip()
        lignes = lignes[1:]
    contenu = " ".join(l.strip() for l in lignes if l.strip())
    con.execute(
        "INSERT INTO fiches(titre, contenu, fichier) VALUES (?, ?, ?)",
        (titre, contenu, f.name),
    )
    n += 1

con.commit()
con.close()
print(f"{n} fiches indexées")
```

## Vérification

```bash
python ingest.py fiches
sqlite3 meshia.db "SELECT titre FROM fiches"
sqlite3 meshia.db "SELECT titre FROM fiches WHERE fiches MATCH 'brulure*'"
```

Si `sqlite3` n'est pas installé : `sudo apt install sqlite3`.
Si l'erreur `no such module: fts5` apparaît : vérifier avec `python -c "import sqlite3; print(sqlite3.sqlite_version)"` ; FTS5 est normalement inclus dans le Python de Debian 12.
