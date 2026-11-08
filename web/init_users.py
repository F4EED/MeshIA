"""Cree secret.key et users.json (chmod 600) s'ils manquent.

Usage (mot de passe lu sur stdin, une ligne) :
  python web/init_users.py meshia
"""
import json
import os
import stat
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT = Path(os.environ.get("MESHIA_ROOT", "/opt/meshia"))
WEB = ROOT / "web"
SECRET = Path(os.environ.get("MESHIA_WEB_SECRET", str(WEB / "secret.key")))
USERS = Path(os.environ.get("MESHIA_WEB_USERS", str(WEB / "users.json")))


def _chmod600(path: Path) -> None:
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: init_users.py <username>", file=sys.stderr)
        sys.exit(2)
    username = sys.argv[1].strip()
    if not username:
        print("nom d'utilisateur vide", file=sys.stderr)
        sys.exit(2)

    WEB.mkdir(parents=True, exist_ok=True)

    if not SECRET.exists():
        SECRET.write_text(os.urandom(32).hex(), encoding="utf-8")
        _chmod600(SECRET)
        print(f"cle session creee : {SECRET}")
    else:
        print(f"cle session deja presente : {SECRET}")

    if USERS.exists():
        print(f"utilisateurs deja presents : {USERS} (inchange)")
        return

    password = sys.stdin.readline().rstrip("\n")
    if not password:
        print("mot de passe vide (stdin)", file=sys.stderr)
        sys.exit(2)

    hashed = generate_password_hash(password, method="scrypt")
    USERS.write_text(json.dumps({username: hashed}, indent=2) + "\n", encoding="utf-8")
    _chmod600(USERS)
    print(f"compte {username} cree dans {USERS}")


if __name__ == "__main__":
    main()
