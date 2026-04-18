"""
main.py — Pipeline complet d'analyse automatique des réclamations SAV Atlantem.

Usage :
    python main.py --week 11 --output output/
    python main.py --week 13 --output output/ --evaluate
    python main.py --week 11 --week 13 --output output/ --evaluate

Variables d'environnement utiles :
    AWS_REGION, BEDROCK_MODEL_ID, ATTACHMENTS_DIR, OUTPUT_DIR, LOG_DIR, BATCH_SIZE
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Chemins par défaut des fichiers de données
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")

WEEK11_COMPLAINTS = DATA_DIR / "week11" / "CustomerComplaints_Week11.CSV"
WEEK11_LINKING    = DATA_DIR / "week11" / "FilesLinkingTable_Week11.CSV"

WEEK13_EXCEL   = DATA_DIR / "week13" / "Reclamations_Digit_20260323-20260327.xlsx"
WEEK13_LINKING = DATA_DIR / "week13" / "Lien_Reclamation_PJ_20260323-20260327.CSV"

ATTACHMENTS_DIR = DATA_DIR / "attachments"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    log_file = log_dir / f"sav_analyzer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger(__name__).info("Journal initialisé : %s", log_file)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    weeks: list[str],
    output_dir: Path,
    attachments_dir: Path,
    model_id: str,
    aws_region: str,
    batch_size: int,
    evaluate: bool,
) -> None:
    from src.data_loader import load_week11, load_week13, Claim
    from src.image_loader import resolve_attachments
    from src.classifier import SAVClassifier, ClassificationResult
    from src.exporter import export_results
    from src.evaluator import evaluate as eval_fn, print_report

    logger = logging.getLogger(__name__)
    classifier = SAVClassifier(model_id=model_id, aws_region=aws_region)

    all_claims: list[Claim] = []
    all_results: list[ClassificationResult] = []

    # --- Chargement des données ---
    if "11" in weeks:
        claims_w11 = load_week11(WEEK11_COMPLAINTS, WEEK11_LINKING)
        all_claims.extend(claims_w11)
        logger.info("Week11 : %d réclamations chargées", len(claims_w11))

    if "13" in weeks:
        claims_w13 = load_week13(WEEK13_EXCEL, WEEK13_LINKING)
        all_claims.extend(claims_w13)
        logger.info("Week13 : %d réclamations chargées", len(claims_w13))

    if not all_claims:
        logger.error("Aucune réclamation chargée. Vérifiez les fichiers d'entrée.")
        sys.exit(1)

    logger.info("Total : %d réclamations à classifier", len(all_claims))

    # --- Classification par lots ---
    start_time = time.time()
    errors = 0

    for i in range(0, len(all_claims), batch_size):
        batch = all_claims[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(all_claims) + batch_size - 1) // batch_size
        logger.info("Lot %d/%d — %d réclamations", batch_num, total_batches, len(batch))

        for claim in batch:
            attachments = resolve_attachments(claim.attachments, attachments_dir)
            result = classifier.classify(claim, attachments)
            all_results.append(result)
            if result.error:
                errors += 1

    elapsed = time.time() - start_time
    logger.info(
        "Classification terminée en %.1fs — %d OK, %d erreurs",
        elapsed, len(all_results) - errors, errors,
    )

    # --- Export CSV ---
    output_path = export_results(all_claims, all_results, output_dir)
    print(f"\n✓ CSV de sortie : {output_path}")
    print(f"  {len(all_claims)} réclamations | {errors} erreurs | {elapsed:.1f}s")

    # --- Évaluation (week13 uniquement) ---
    if evaluate:
        week13_claims = [c for c in all_claims if c.ref_type_litige]
        week13_results = [r for r in all_results if any(
            c.id == r.claim_id and c.ref_type_litige for c in week13_claims
        )]
        if week13_claims:
            report = eval_fn(week13_claims, week13_results)
            print_report(report)
        else:
            logger.warning("Aucune réclamation week13 avec labels de référence pour l'évaluation.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse automatique des réclamations SAV Atlantem",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python main.py --week 11
  python main.py --week 13 --evaluate
  python main.py --week 11 --week 13 --output output/ --evaluate
        """,
    )
    parser.add_argument(
        "--week", "-w",
        choices=["11", "13"],
        action="append",
        dest="weeks",
        default=None,
        help="Semaine(s) à traiter (11 et/ou 13). Défaut : 13",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output"),
        help="Répertoire de sortie (défaut : ./output)",
    )
    parser.add_argument(
        "--attachments",
        type=Path,
        default=ATTACHMENTS_DIR,
        help=f"Répertoire des pièces jointes (défaut : {ATTACHMENTS_DIR})",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Identifiant du modèle Bedrock (surcharge BEDROCK_MODEL_ID)",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Région AWS (surcharge AWS_REGION)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Taille des lots (défaut : 100)",
    )
    parser.add_argument(
        "--evaluate", "-e",
        action="store_true",
        help="Comparer les résultats avec les labels week13 et afficher la précision",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs"),
        help="Répertoire des journaux (défaut : ./logs)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Niveau de journalisation (défaut : INFO)",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    setup_logging(args.log_dir, args.log_level)
    logger = logging.getLogger(__name__)

    # Valeurs par défaut
    weeks = args.weeks or ["13"]

    import os
    model_id = args.model or os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    aws_region = args.region or os.environ.get("AWS_REGION", "eu-west-1")

    logger.info("Démarrage — semaines=%s, modèle=%s, région=%s", weeks, model_id, aws_region)

    run_pipeline(
        weeks=weeks,
        output_dir=args.output,
        attachments_dir=args.attachments,
        model_id=model_id,
        aws_region=aws_region,
        batch_size=args.batch_size,
        evaluate=args.evaluate,
    )


if __name__ == "__main__":
    main()
