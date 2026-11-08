"""Test logique radio : aide, zzzz, blackout → liste, titre → une fiche."""
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["MESHIA_DB"] = db.name
os.environ["MESHIA_LLM"] = "0"
os.environ.setdefault("MESHIA_MAXLEN", "130")
os.environ.setdefault("MESHIA_MAXPARTS", "3")

subprocess.check_call(
    [sys.executable, str(ROOT / "ingest.py"), str(ROOT / "fiches")],
    cwd=str(ROOT),
    env=os.environ.copy(),
)

sys.path.insert(0, str(ROOT))
from meshia import MAX_OCTETS, MAX_PARTS, parts_pour_question  # noqa: E402


def _ok_parts(parts, nmax=None):
    assert parts, "aucune part"
    assert len(parts) <= (nmax if nmax is not None else MAX_PARTS)
    for p in parts:
        assert len(p.encode("utf-8")) <= MAX_OCTETS + 8, p


aide = parts_pour_question("aide")
_ok_parts(aide)
assert "Sujets" in " ".join(aide), aide

zzzz = parts_pour_question("zzzz")
_ok_parts(zzzz)
assert "Rien trouvé" in " ".join(zzzz), zzzz

blackout = parts_pour_question("blackout")
_ok_parts(blackout, nmax=1)
texte = " ".join(blackout)
assert "Lequel" in texte, blackout
assert "énergie" in texte.lower() or "energie" in texte.lower(), blackout
assert "télécom" in texte.lower() or "telecom" in texte.lower(), blackout
assert "Coupure générale" not in texte, blackout
assert len(blackout[0].encode("utf-8")) <= MAX_OCTETS, blackout[0]

telecom = parts_pour_question("Blackout télécom")
_ok_parts(telecom)
t2 = " ".join(telecom)
assert "télécom" in t2.lower() or "telecom" in t2.lower() or "mobile" in t2.lower(), telecom
assert "Coupure générale" not in t2, telecom

print("OK", len(aide), "aide,", len(zzzz), "zzzz,", len(blackout), "blackout,", len(telecom), "titre")
print("blackout:", blackout)
print("titre:", telecom[0][:80])
