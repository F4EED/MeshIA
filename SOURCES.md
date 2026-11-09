# Sources des fiches MeshIA (lot preparation / Loire / FR-Alert)

Consultation : **9 novembre 2026**, fuseau **Europe/Paris**.
Statut des fiches de ce lot : **a valider** (regle 03-fiches.md du depot F4EED/MeshIA : relire avec source officielle avant usage reel).
Lot pousse sur main MeshIA (voir historique git).

## Regle de format appliquee

- Un fichier `.md` = un sujet ; titre `# Mot-cle` = mot que l utilisateur taperait.
- Essentiel dans les ~120 premiers caracteres ; phrases courtes.
- Pas de tableaux, pas de liens, pas d emojis ; synonymes en fin de fiche.
- Pas de metadonnees dans le `.md` (le depot n en prevoit pas) : sources ici.

## FR-Alert — messages des 48 dernieres heures

Fenetre demandee : depuis le **7 nov. 2026 ~12h15** Europe/Paris jusqu a la generation.
Source : https://fr-alert.gouv.fr/les-alertes (HTML Drupal rendu cote serveur, lisible au curl sans navigateur ; **pas d API publique documentee**).
Resultat au 9 nov. 2026 ~12h20 Europe/Paris : **0 alerte** dans la fenetre (derniere entree du registre : **5 nov. 2026 07h05** — Inondation rapide, Corse-du-Sud secteur Est).
Exercices annonces (Finistere Guipavas 9 nov. matin, Mayenne Mont des Avaloirs 9 nov. 14h30) : **non listes** sur le registre au moment de la lecture ; **aucune fiche par alerte creee**.
Script : `tools/fralert_48h.py` — lit la page, filtre 48 h, ecrit `fiches/fr-alert/fr-alert-*.md`, supprime les anciennes hors fenetre.

## Sources nationales retenues

| # | Titre | URL | Fiches alimentees |
|---|-------|-----|-------------------|
| 1 | Se preparer a une situation d urgence | https://www.info.gouv.fr/risques/se-preparer-a-une-situation-durgence | preparation, pendant-crise, apres-crise, reserve-72h, documents, fr-alert (contexte), sirene |
| 2 | Guide Tous responsables (SGDSN, PDF) | https://www.defense.gouv.fr/sites/default/files/ministere-armees/SGDSN_Guide_Tous%20responsables.pdf (miroir ; URL sgdsn.gouv.fr a aussi ete tentee) | preparation, reserve-72h, pendant-crise |
| 3 | Kit d urgence 72 h (Georisques / ecologie) | https://www.georisques.gouv.fr/me-preparer-me-proteger/mon-kit-durgence-72h | reserve-72h, documents (complement de kit72h existant) |
| 3b | Infographie kit (PDF info.gouv) | https://www.info.gouv.fr/upload/media/mixed/0001/15/0f52e90c8641ac288227151331c995a566d14fdb.pdf | reserve-72h |
| 4 | PIMS Prets ? Pares ! (PDF) | https://www.securite-civile.interieur.gouv.fr/sites/securitecivile/files/medias/documents/2025-08/maquette-PIMS-Fr-net.pdf | pims, industriel, tmd, feu-foret, barrage, sirene, fr-alert |
| 5 | PFMS Je me protege en famille (PDF) | https://www.georisques.gouv.fr/sites/default/files/2022-08/PFMS_jeprotegemafamille-1.pdf | pfms, documents, pendant-crise |
| 6 | Comment se preparer face aux risques | https://www.securite-civile.interieur.gouv.fr/reagir/comment-se-preparer-face-aux-risques | pims, preparation, orsec |
| — | FAQ FR-Alert | https://fr-alert.gouv.fr/foire-aux-questions | fr-alert |
| — | Registre des alertes FR-Alert | https://fr-alert.gouv.fr/les-alertes | fiches/fr-alert/* (vide sur 48 h) |

## Sources Loire

| # | Titre | URL | Fiches |
|---|-------|-----|--------|
| 10 | DDRM Loire (page) | https://www.loire.gouv.fr/Actions-de-l-Etat/Risques-naturels.-miniers-et-technologiques/Dossier-departemental-des-Risques-Majeurs-DDRM | ddrm-loire |
| 11 | DDRM Loire 2023 (PDF) | https://www.loire.gouv.fr/contenu/telechargement/11103/82708/file/DDRM%202023.pdf | ddrm-loire, sirene, fr-alert, industriel, tmd, radon, barrage, nucleaire-loire, feu-foret, canicule-vigilance |
| 12 | La gestion de crise (Loire) | https://www.loire.gouv.fr/Actions-de-l-Etat/Securite-des-personnes-et-des-biens/Securite-civile/La-gestion-de-crise | orsec, maire, prefet, barrage |
| 14 | Guide PCS vague de chaleur Loire 2024 (PDF) | https://www.loire.gouv.fr/contenu/telechargement/24167/176482/file/Guide%20PCS%20vague%20de%20chaleur%202024.pdf | canicule-vigilance (angle vigilance / organisation ; gestes citoyens aussi dans canicule existant) |

## Doublons / chevauchements avec le depot

Sujets **deja presents** dans `F4EED/MeshIA/fiches/` : ne pas ecraser. Complements proposes dans ce lot :

| Existant | Complement cree | Nature |
|----------|-----------------|--------|
| kit72h.md | reserve-72h.md, documents.md | Liste officielle 6 L / pieces |
| confinement.md, toxique.md | industriel.md, tmd.md | Angle Seveso / TMD Loire |
| evacuation.md | pendant-crise.md, pfms.md | Quand partir / plan famille |
| canicule.md | canicule-vigilance.md | Niveaux vigilance |
| inondation.md | barrage.md | Specifique rupture ouvrage |
| incendie.md | feu-foret.md | Feu de vegetation |
| nucleaire.md | nucleaire-loire.md | Saint-Alban / iode prefet |
| seisme.md | (aucun nouveau) | Deja couvert ; PIMS renvoie aux memes gestes |
| urgence.md | (aucun nouveau) | Deja 15/18/112/114 |
| signaux.md | sirene.md | Signaux.md = detresse survie ; sirene = SAIP |
| eau.md / nourriture.md | reserve-72h.md | Stock vs purification / rations |
| vigicrue.md, vigilance-meteo.md, vigipirate.md | (inchanges) | Deja dans le depot / dossier local |

## Sources inaccessibles ou degradees

- `https://www.sgdsn.gouv.fr/files/files/Publications/Tous%20responsables%20-%20Web.pdf` : premiere tentative a renvoye un petit fichier non PDF ; **miroir defense.gouv.fr utilise avec succes**.
- Pages `*.gouv.fr` : curl peut echouer en verification TLS (chaine Sectigo) ; contournement `-k` / contexte SSL non verifie dans le script (lecture publique uniquement).
- WebFetch sur fr-alert.gouv.fr/les-alertes : timeout intermittent ; **curl OK** (~5 Mo HTML).

## Automatisation FR-Alert

```bash
python3 `tools/fralert_48h.py`
# ou :
python3 `tools/fralert_48h.py` --hours 48 --outdir fiches/fr-alert
```

Pas d API officielle ; le script parse le HTML de `/les-alertes` puis optionnellement la page detail pour le message de consignes.
