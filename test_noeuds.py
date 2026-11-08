"""ACL nœuds : inconnu → attente, autorisé → ok, refusé → un refus puis silence."""
import os
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
os.environ["MESHIA_NOEUDS"] = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
import sys

sys.path.insert(0, str(ROOT))
from noeuds import MSG_ATTENTE, MSG_REFUS, decision_mp, par_statut, set_statut  # noqa: E402


def contact(nom, pk):
    return {"name": nom, "public_key": pk}


prefix = "aabbccdd"
pk = "aabbccdd00112233445566778899aabbccddeeff00112233445566778899aabb"

a, msg, ident, nom, pref = decision_mp(contact("Frederic", pk), prefix)
assert a == "attente" and msg == MSG_ATTENTE, (a, msg)
assert nom == "Frederic"
assert ident == pk
assert par_statut()["attente"][0]["nom"] == "Frederic"

a2, _, _, _, _ = decision_mp(contact("Frederic", pk), prefix)
assert a2 == "attente"

set_statut(pk, "autorise")
ok, msg_ok, _, _, _ = decision_mp(contact("Frederic", pk), prefix)
assert ok == "ok" and msg_ok is None, (ok, msg_ok)
assert par_statut()["autorise"][0]["pubkey"] == pk

set_statut(pk, "refuse")
r1, m1, _, _, _ = decision_mp(contact("Frederic", pk), prefix)
assert r1 == "refus" and m1 == MSG_REFUS, (r1, m1)
from noeuds import marquer_refuse_notifie

marquer_refuse_notifie(pk, prefix)
r2, m2, _, _, _ = decision_mp(contact("Frederic", pk), prefix)
assert r2 == "silence" and m2 is None, (r2, m2)

set_statut(pk, "autorise")
ok2, _, _, _, _ = decision_mp(contact("Frederic", pk), prefix)
assert ok2 == "ok"

print("OK attente / autoriser / refuser-une-fois / réautoriser")
