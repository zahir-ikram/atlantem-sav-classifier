"""
evaluator.py — Évaluation de la précision des classifications IA vs labels de référence (week13).

Compare les 4 champs classifiés par l'IA avec les labels humains du fichier week13
et affiche le pourcentage de précision par champ et global.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.classifier import ClassificationResult
from src.data_loader import Claim

logger = logging.getLogger(__name__)

FIELDS = ["type_litige", "responsabilite", "solution", "precision_produit"]

FIELD_LABELS = {
    "type_litige":       "Type de litige",
    "responsabilite":    "Responsabilité",
    "solution":          "Solution",
    "precision_produit": "Précision produit",
}


@dataclass
class EvaluationReport:
    """Rapport de précision par champ et global."""
    total: int
    evaluated: int  # réclamations avec labels de référence non vides
    per_field: dict[str, float]   # {field: accuracy_pct}
    overall: float                # moyenne des 4 champs


def evaluate(
    claims: list[Claim],
    results: list[ClassificationResult],
) -> EvaluationReport:
    """
    Compare les résultats IA avec les labels de référence des réclamations week13.

    Seules les réclamations ayant au moins un label de référence non vide sont évaluées.

    Args:
        claims:  Liste des réclamations (avec ref_* renseignés pour week13).
        results: Liste des résultats de classification IA.

    Returns:
        Un :class:`EvaluationReport` avec les précisions par champ et globale.
    """
    result_map: dict[str, ClassificationResult] = {r.claim_id: r for r in results}

    # Compteurs par champ
    correct: dict[str, int] = {f: 0 for f in FIELDS}
    total_per_field: dict[str, int] = {f: 0 for f in FIELDS}
    evaluated = 0

    for claim in claims:
        ref = {
            "type_litige":       claim.ref_type_litige,
            "responsabilite":    claim.ref_responsabilite,
            "solution":          claim.ref_solution,
            "precision_produit": claim.ref_precision_produit,
        }

        # Ignorer les réclamations sans aucun label de référence
        if not any(v for v in ref.values()):
            continue

        res = result_map.get(claim.id)
        if res is None or res.error:
            continue

        evaluated += 1

        for field in FIELDS:
            ref_val = ref[field].strip()
            if not ref_val:
                continue  # pas de label pour ce champ

            pred_val = getattr(res, field, "").strip()
            total_per_field[field] += 1

            # Comparaison insensible à la casse et aux espaces
            if ref_val.lower() == pred_val.lower():
                correct[field] += 1
            else:
                logger.debug(
                    "Désaccord %s | %s | attendu='%s' prédit='%s'",
                    claim.id, field, ref_val, pred_val,
                )

    # Calcul des précisions
    per_field: dict[str, float] = {}
    for field in FIELDS:
        n = total_per_field[field]
        per_field[field] = (correct[field] / n * 100) if n > 0 else 0.0

    overall = sum(per_field.values()) / len(FIELDS) if FIELDS else 0.0

    return EvaluationReport(
        total=len(claims),
        evaluated=evaluated,
        per_field=per_field,
        overall=overall,
    )


def print_report(report: EvaluationReport) -> None:
    """Affiche le rapport de précision dans la console."""
    separator = "─" * 45
    print(f"\n{separator}")
    print("  RAPPORT D'ÉVALUATION — SAV Claims Analyzer")
    print(separator)
    print(f"  Réclamations totales   : {report.total}")
    print(f"  Réclamations évaluées  : {report.evaluated}")
    print(separator)
    for field in FIELDS:
        label = FIELD_LABELS[field]
        pct = report.per_field[field]
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {label:<22} {bar} {pct:5.1f}%")
    print(separator)
    print(f"  Précision globale      : {report.overall:5.1f}%")
    print(f"{separator}\n")
