"""
data_loader.py — Chargement des réclamations SAV depuis les fichiers week11 et week13.

Week11 :
  - CustomerComplaints_Week11.CSV  → réclamations (séparateur ;, encodage Latin-1)
  - FilesLinkingTable_Week11.CSV   → mapping identifiant → fichiers joints

Week13 :
  - Reclamations_Digit_20260323-20260327.xlsx → deux tableaux côte à côte :
      colonnes 1-8  : réclamation brute
      colonnes 10-14: labels de référence (Type de litige, Responsabilité, Solution, Précision produit)
  - Lien_Reclamation_PJ_20260323-20260327.CSV → mapping identifiant → fichiers joints
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import chardet
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    """Représente une réclamation SAV."""
    id: str
    code_client: str
    type_produit: str
    num_commande: str
    reperes: str
    description: str
    souhait: str
    numero_ligne: str
    attachments: list[str] = field(default_factory=list)
    # Labels de référence (week13 uniquement)
    ref_type_litige: str = ""
    ref_responsabilite: str = ""
    ref_solution: str = ""
    ref_precision_produit: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_encoding(path: Path) -> str:
    """Détecte l'encodage d'un fichier texte via chardet."""
    raw = path.read_bytes()
    result = chardet.detect(raw)
    encoding = result.get("encoding") or "utf-8"
    logger.debug("Encodage détecté pour %s : %s (confiance %.0f%%)",
                 path.name, encoding, (result.get("confidence") or 0) * 100)
    return encoding


def _read_csv_auto(path: Path, sep: str = ";") -> pd.DataFrame:
    """Lit un CSV en détectant automatiquement l'encodage."""
    encoding = _detect_encoding(path)
    try:
        return pd.read_csv(path, sep=sep, encoding=encoding, dtype=str)
    except UnicodeDecodeError:
        logger.warning("Échec lecture avec %s, tentative en latin-1", encoding)
        return pd.read_csv(path, sep=sep, encoding="latin-1", dtype=str)


def _build_attachment_map(linking_path: Path) -> dict[str, list[str]]:
    """
    Construit un dict {identifiant_reclamation: [fichier1, fichier2, ...]}
    depuis un fichier de liaison (colonnes Reference;Fichier).

    La colonne Reference contient des valeurs de la forme :
        R20260309002#SAVF-48278-260007
    On extrait la partie avant le '#' comme identifiant de réclamation.
    """
    df = _read_csv_auto(linking_path)
    mapping: dict[str, list[str]] = {}

    if "Reference" not in df.columns or "Fichier" not in df.columns:
        logger.warning("Colonnes Reference/Fichier introuvables dans %s", linking_path.name)
        return mapping

    for _, row in df.iterrows():
        ref = str(row["Reference"]).strip()
        fichier = str(row["Fichier"]).strip()
        # L'identifiant de réclamation est la partie avant '#'
        claim_id = ref.split("#")[0] if "#" in ref else ref
        mapping.setdefault(claim_id, []).append(fichier)

    return mapping


# ---------------------------------------------------------------------------
# Week 11
# ---------------------------------------------------------------------------

def load_week11(
    complaints_path: Path,
    linking_path: Path,
) -> list[Claim]:
    """
    Charge les réclamations de la semaine 11.

    Args:
        complaints_path: Chemin vers CustomerComplaints_Week11.CSV
        linking_path:    Chemin vers FilesLinkingTable_Week11.CSV

    Returns:
        Liste de :class:`Claim` avec les pièces jointes résolues.
    """
    logger.info("Chargement week11 : %s", complaints_path.name)
    df = _read_csv_auto(complaints_path)

    # Colonnes attendues
    expected = {"identifiant", "codeClient", "typeProduit",
                "numCdeOrigine", "reperesConcernes", "description",
                "souhait", "numeroLigne"}
    missing_cols = expected - set(df.columns)
    if missing_cols:
        raise ValueError(f"Colonnes manquantes dans {complaints_path.name} : {missing_cols}")

    attachment_map = _build_attachment_map(linking_path)
    claims: list[Claim] = []

    for idx, row in df.iterrows():
        claim_id = str(row.get("identifiant", "")).strip()
        description = str(row.get("description", "")).strip()

        if not description or description.lower() == "nan":
            logger.warning("Ligne %d ignorée (description vide) : %s", idx, claim_id)
            continue

        # L'identifiant de réclamation dans la table de liaison est la partie avant '#'
        short_id = claim_id.split("#")[0] if "#" in claim_id else claim_id

        claims.append(Claim(
            id=claim_id,
            code_client=str(row.get("codeClient", "")).strip(),
            type_produit=str(row.get("typeProduit", "")).strip(),
            num_commande=str(row.get("numCdeOrigine", "")).strip(),
            reperes=str(row.get("reperesConcernes", "")).strip(),
            description=description,
            souhait=str(row.get("souhait", "")).strip(),
            numero_ligne=str(row.get("numeroLigne", "")).strip(),
            attachments=attachment_map.get(short_id, []),
        ))

    logger.info("Week11 : %d réclamations chargées", len(claims))
    return claims


# ---------------------------------------------------------------------------
# Week 13
# ---------------------------------------------------------------------------

def load_week13(
    excel_path: Path,
    linking_path: Path,
) -> list[Claim]:
    """
    Charge les réclamations de la semaine 13 depuis le fichier Excel.

    Le fichier contient deux tableaux côte à côte (header sur la ligne 1, index 0-based) :
      - Colonnes B-I  (index 1-8)  : données de réclamation
      - Colonnes K-O  (index 10-14): labels de référence

    Args:
        excel_path:   Chemin vers Reclamations_Digit_20260323-20260327.xlsx
        linking_path: Chemin vers Lien_Reclamation_PJ_20260323-20260327.CSV

    Returns:
        Liste de :class:`Claim` avec labels de référence et pièces jointes.
    """
    logger.info("Chargement week13 : %s", excel_path.name)

    # Lire sans header — la ligne 1 (index 1) contient les vrais noms de colonnes
    raw = pd.read_excel(excel_path, header=None, dtype=str)

    # Ligne 1 = noms de colonnes pour les deux tableaux
    header_row = raw.iloc[1].tolist()

    # Tableau réclamation : colonnes 1-8
    claim_cols = header_row[1:9]   # identifiant, codeClient, typeProduit, ...
    df_claims = raw.iloc[2:, 1:9].copy()
    df_claims.columns = claim_cols
    df_claims = df_claims.reset_index(drop=True)

    # Tableau labels : colonnes 10-14
    label_cols = header_row[10:15]  # identifiant, Type de litige, Responsabilité, Solution, Précision produit
    df_labels = raw.iloc[2:, 10:15].copy()
    df_labels.columns = label_cols
    df_labels = df_labels.reset_index(drop=True)

    # Construire un dict {identifiant: labels} depuis le tableau de droite
    label_map: dict[str, dict] = {}
    id_col_label = label_cols[0]  # "identifiant"
    for _, row in df_labels.iterrows():
        lid = str(row.get(id_col_label, "")).strip()
        if lid and lid.lower() != "nan":
            label_map[lid] = {
                "type_litige":       str(row.get("Type de litige", "")).strip(),
                "responsabilite":    str(row.get("Responsabilité", "")).strip(),
                "solution":          str(row.get("Solution", "")).strip(),
                "precision_produit": str(row.get("Précision produit", "")).strip(),
            }

    attachment_map = _build_attachment_map(linking_path)
    claims: list[Claim] = []

    for idx, row in df_claims.iterrows():
        claim_id = str(row.get("identifiant", "")).strip()
        description = str(row.get("description", "")).strip()

        if not claim_id or claim_id.lower() == "nan":
            continue
        if not description or description.lower() == "nan":
            logger.warning("Ligne %d ignorée (description vide) : %s", idx, claim_id)
            continue

        short_id = claim_id.split("#")[0] if "#" in claim_id else claim_id
        labels = label_map.get(claim_id, {})

        claims.append(Claim(
            id=claim_id,
            code_client=str(row.get("codeClient", "")).strip(),
            type_produit=str(row.get("typeProduit", "")).strip(),
            num_commande=str(row.get("numCdeOrigine", "")).strip(),
            reperes=str(row.get("reperesConcernes", "")).strip(),
            description=description,
            souhait=str(row.get("souhait", "")).strip(),
            numero_ligne=str(row.get("numeroLigne", "")).strip(),
            attachments=attachment_map.get(short_id, []),
            ref_type_litige=labels.get("type_litige", ""),
            ref_responsabilite=labels.get("responsabilite", ""),
            ref_solution=labels.get("solution", ""),
            ref_precision_produit=labels.get("precision_produit", ""),
        ))

    logger.info("Week13 : %d réclamations chargées", len(claims))
    return claims
