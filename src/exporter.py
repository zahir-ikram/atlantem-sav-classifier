"""
exporter.py — Écriture du CSV de sortie enrichi avec les 4 champs de classification.

Encodage : UTF-8 avec BOM (utf-8-sig) pour compatibilité Excel.
Nom du fichier : output_YYYYMMDD_HHMMSS.csv
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from src.classifier import ClassificationResult
from src.data_loader import Claim

logger = logging.getLogger(__name__)

# Colonnes ajoutées par le classificateur
CLASSIFICATION_COLUMNS = [
    "type_litige",
    "type_litige_confidence",
    "responsabilite",
    "responsabilite_confidence",
    "solution",
    "solution_confidence",
    "precision_produit",
    "precision_produit_confidence",
    "erreur",
]


def export_results(
    claims: list[Claim],
    results: list[ClassificationResult],
    output_dir: Path,
) -> Path:
    """
    Écrit un CSV enrichi avec les classifications.

    Les colonnes d'origine de chaque réclamation sont conservées, suivies
    des 4 champs de classification, leurs scores de confiance et une colonne erreur.

    Args:
        claims:     Liste des réclamations d'entrée (même ordre que results).
        results:    Liste des résultats de classification.
        output_dir: Répertoire de sortie.

    Returns:
        Chemin du fichier CSV produit.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"output_{timestamp}.csv"

    # Colonnes de base (ordre fixe)
    base_columns = [
        "id", "code_client", "type_produit", "num_commande",
        "reperes", "description", "souhait", "numero_ligne",
    ]
    all_columns = base_columns + CLASSIFICATION_COLUMNS

    result_map: dict[str, ClassificationResult] = {r.claim_id: r for r in results}

    with output_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=all_columns, extrasaction="ignore")
        writer.writeheader()

        for claim in claims:
            res = result_map.get(claim.id)
            row: dict = {
                "id":           claim.id,
                "code_client":  claim.code_client,
                "type_produit": claim.type_produit,
                "num_commande": claim.num_commande,
                "reperes":      claim.reperes,
                "description":  claim.description,
                "souhait":      claim.souhait,
                "numero_ligne": claim.numero_ligne,
            }

            if res is None:
                row.update({col: "" for col in CLASSIFICATION_COLUMNS})
                row["erreur"] = "Résultat manquant"
            elif res.error:
                row.update({
                    "type_litige":                "",
                    "type_litige_confidence":     "",
                    "responsabilite":             "",
                    "responsabilite_confidence":  "",
                    "solution":                   "",
                    "solution_confidence":        "",
                    "precision_produit":          "",
                    "precision_produit_confidence": "",
                    "erreur": res.error,
                })
            else:
                row.update({
                    "type_litige":                res.type_litige,
                    "type_litige_confidence":     f"{res.type_litige_confidence:.2f}",
                    "responsabilite":             res.responsabilite,
                    "responsabilite_confidence":  f"{res.responsabilite_confidence:.2f}",
                    "solution":                   res.solution,
                    "solution_confidence":        f"{res.solution_confidence:.2f}",
                    "precision_produit":          res.precision_produit,
                    "precision_produit_confidence": f"{res.precision_produit_confidence:.2f}",
                    "erreur": "",
                })

            writer.writerow(row)

    logger.info("CSV de sortie écrit : %s (%d lignes)", output_path, len(claims))
    return output_path
