"""
data_loader.py — Chargement des réclamations SAV depuis les fichiers Excel unifiés.

Format des fichiers Excel :
- Colonnes : identifiant, codeClient, typeProduit, numCdeOrigine, reperesConcernes, 
             description, souhait, numeroLigne, Images, [Type de litige, Responsabilité, 
             Solution, Précision produit] (seulement pour week13)
- Colonne "Images" : liste de fichiers séparés par des points-virgules
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

def _parse_images_column(images_str: str) -> list[str]:
    """
    Parse la colonne Images qui contient des noms de fichiers séparés par des points-virgules.
    Ex: "80c3ca5a051a59f95555441c44cfeca2.jpg;972c93ae9a148ac91ef0f1f4cde1a7b8.jpg"
    """
    if not images_str or str(images_str).lower() == "nan":
        return []
    # Split par point-virgule et nettoyer les espaces
    return [f.strip() for f in str(images_str).split(";") if f.strip()]


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


# ---------------------------------------------------------------------------
# Week 11
# ---------------------------------------------------------------------------

def load_week11(excel_path: Path) -> list[Claim]:
    """
    Charge les réclamations de la semaine 11 depuis le fichier Excel unifié.

    Args:
        excel_path: Chemin vers data_test.xlsx (Week 11)

    Returns:
        Liste de :class:`Claim` avec les pièces jointes résolues.
    """
    logger.info("Chargement week11 : %s", str(excel_path))
    df = pd.read_excel(excel_path, dtype=str)

    # Colonnes attendues
    expected = {"identifiant", "codeClient", "typeProduit",
                "numCdeOrigine", "reperesConcernes", "description",
                "souhait", "numeroLigne", "Images"}
    missing_cols = expected - set(df.columns)
    if missing_cols:
        raise ValueError(f"Colonnes manquantes dans {excel_path.name} : {missing_cols}")

    claims: list[Claim] = []

    for idx, row in df.iterrows():
        claim_id = str(row.get("identifiant", "")).strip()
        description = str(row.get("description", "")).strip()

        if not description or description.lower() == "nan":
            logger.warning("Ligne %d ignorée (description vide) : %s", idx, claim_id)
            continue

        # Parse la colonne Images (points-virgules)
        images_str = str(row.get("Images", "")).strip()
        attachments = _parse_images_column(images_str)

        claims.append(Claim(
            id=claim_id,
            code_client=str(row.get("codeClient", "")).strip(),
            type_produit=str(row.get("typeProduit", "")).strip(),
            num_commande=str(row.get("numCdeOrigine", "")).strip(),
            reperes=str(row.get("reperesConcernes", "")).strip(),
            description=description,
            souhait=str(row.get("souhait", "")).strip(),
            numero_ligne=str(row.get("numeroLigne", "")).strip(),
            attachments=attachments,
        ))

    logger.info("Week11 : %d réclamations chargées", len(claims))
    return claims


# ---------------------------------------------------------------------------
# Week 13
# ---------------------------------------------------------------------------

def load_week13(excel_path: Path) -> list[Claim]:
    """
    Charge les réclamations de la semaine 13 depuis le fichier Excel unifié.

    Le fichier contient les labels de référence directement dans les colonnes :
    Type de litige, Responsabilité, Solution, Précision produit

    Args:
        excel_path: Chemin vers data_train.xlsx (Week 13)

    Returns:
        Liste de :class:`Claim` avec labels de référence et pièces jointes.
    """
    logger.info("Chargement week13 : %s", str(excel_path))
    df = pd.read_excel(excel_path, dtype=str)

    # Colonnes attendues
    expected = {"identifiant", "codeClient", "typeProduit",
                "numCdeOrigine", "reperesConcernes", "description",
                "souhait", "numeroLigne", "Images",
                "Type de litige", "Responsabilité", "Solution", "Précision produit"}
    missing_cols = expected - set(df.columns)
    if missing_cols:
        raise ValueError(f"Colonnes manquantes dans {excel_path.name} : {missing_cols}")

    claims: list[Claim] = []

    for idx, row in df.iterrows():
        claim_id = str(row.get("identifiant", "")).strip()
        description = str(row.get("description", "")).strip()

        if not claim_id or claim_id.lower() == "nan":
            continue
        if not description or description.lower() == "nan":
            logger.warning("Ligne %d ignorée (description vide) : %s", idx, claim_id)
            continue

        # Parse la colonne Images (points-virgules)
        images_str = str(row.get("Images", "")).strip()
        attachments = _parse_images_column(images_str)

        claims.append(Claim(
            id=claim_id,
            code_client=str(row.get("codeClient", "")).strip(),
            type_produit=str(row.get("typeProduit", "")).strip(),
            num_commande=str(row.get("numCdeOrigine", "")).strip(),
            reperes=str(row.get("reperesConcernes", "")).strip(),
            description=description,
            souhait=str(row.get("souhait", "")).strip(),
            numero_ligne=str(row.get("numeroLigne", "")).strip(),
            attachments=attachments,
            ref_type_litige=str(row.get("Type de litige", "")).strip(),
            ref_responsabilite=str(row.get("Responsabilité", "")).strip(),
            ref_solution=str(row.get("Solution", "")).strip(),
            ref_precision_produit=str(row.get("Précision produit", "")).strip(),
        ))

    logger.info("Week13 : %d réclamations chargées", len(claims))
    return claims
