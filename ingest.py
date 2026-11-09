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
fichiers = list(dossier.glob("*.md"))
# Alertes FR-Alert générées (sous-dossier, un fichier par alerte récente)
fichiers += list((dossier / "fr-alert").glob("*.md")) if (dossier / "fr-alert").is_dir() else []
for f in sorted(set(fichiers), key=lambda x: x.as_posix()):
    lignes = f.read_text(encoding="utf-8").strip().splitlines()
    titre = f.stem
    if lignes and lignes[0].startswith("#"):
        titre = lignes[0].lstrip("# ").strip()
        lignes = lignes[1:]
    contenu = " ".join(l.strip() for l in lignes if l.strip())
    con.execute(
        "INSERT INTO fiches(titre, contenu, fichier) VALUES (?, ?, ?)",
        (titre, contenu, f.relative_to(dossier).as_posix()),
    )
    n += 1

con.commit()
con.close()
print(f"{n} fiches indexées")
