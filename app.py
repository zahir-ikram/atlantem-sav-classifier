"""
app.py — Interface "Conseiller SAV" pour Atlantem.

Lancement :
    streamlit run app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration de la page
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Atlantem SAV Intelligence",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Chemins des données
# ---------------------------------------------------------------------------

DATA_DIR        = Path("data")
ATTACHMENTS_DIR = DATA_DIR / "attachments"

WEEK11_EXCEL = DATA_DIR / "week11" / "data_test.xlsx"
WEEK13_EXCEL = DATA_DIR / "week13" / "data_train.xlsx"

# ---------------------------------------------------------------------------
# Chargement des données (mis en cache)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Chargement des réclamations…")
def load_all_claims() -> list:
    """Charge toutes les réclamations (Week 11 + Week 13) et les trie chronologiquement."""
    from src.data_loader import load_week11, load_week13
    
    # Charger les deux semaines
    claims_w11 = load_week11(WEEK11_EXCEL)
    claims_w13 = load_week13(WEEK13_EXCEL)
    all_claims = claims_w11 + claims_w13
    
    def extract_date_from_id(claim_id: str) -> tuple:
        """Extrait date et index depuis l'ID (ex: R20260323001 -> (2026-03-23, 1))"""
        import re
        match = re.match(r'R(\d{8})(\d{3})', claim_id)
        if match:
            date_str, index_str = match.groups()
            try:
                # Format YYYYMMDD -> datetime
                from datetime import datetime
                date = datetime.strptime(date_str, '%Y%m%d')
                index = int(index_str)
                return (date, index)
            except ValueError:
                pass
        # Fallback : date très ancienne pour les IDs non conformes
        from datetime import datetime
        return (datetime(1900, 1, 1), 0)
    
    # Trier par date puis par index (plus ancien au plus récent)
    all_claims.sort(key=lambda c: extract_date_from_id(c.id))
    
    return all_claims


# ---------------------------------------------------------------------------
# Initialisation du classifier (une seule instance)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Initialisation du modèle IA…")
def get_classifier():
    from src.classifier import SAVClassifier
    model_id   = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    aws_region = os.environ.get("AWS_REGION", "eu-west-1")
    return SAVClassifier(model_id=model_id, aws_region=aws_region)


# ---------------------------------------------------------------------------
# CSS personnalisé
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    .claim-card {
        background: #f8f9fa;
        border-left: 4px solid #0066cc;
        border-radius: 6px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .result-card {
        background: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .result-label {
        font-size: 0.75rem;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.3rem;
    }
    .result-value {
        font-size: 1.1rem;
        font-weight: 700;
        color: #0066cc;
    }
    .ref-badge {
        font-size: 0.72rem;
        color: #888;
        margin-top: 0.2rem;
    }
    .section-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #444;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# En-tête principal
# ---------------------------------------------------------------------------

st.title("🛠️ Atlantem SAV Intelligence")
st.caption("Analyse automatique des réclamations menuiserie industrielle")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📋 Réclamations")

    claims = load_all_claims()

    # Recherche par ID client
    search = st.text_input("🔍 Recherche par ID client", placeholder="ex: PRM049005")

    filtered = claims
    if search.strip():
        filtered = [c for c in claims if search.strip().lower() in c.code_client.lower()]

    if not filtered:
        st.warning("Aucune réclamation trouvée.")
        st.stop()

    # Selectbox : affiche date + ID + type produit
    def format_claim_option(claim):
        # Extraire la date depuis l'ID
        import re
        match = re.match(r'R(\d{8})(\d{3})', claim.id)
        if match:
            date_str = match.groups()[0]
            try:
                from datetime import datetime
                date = datetime.strptime(date_str, '%Y%m%d')
                date_formatted = date.strftime('%d/%m/%Y')
                return f"{date_formatted} • {claim.id} • {claim.type_produit}"
            except ValueError:
                pass
        return f"{claim.id} • {claim.type_produit}"
    
    options = {format_claim_option(c): c for c in filtered}
    selected_label = st.selectbox(
        f"{len(filtered)} réclamation(s) (chronologique)",
        list(options.keys()),
        label_visibility="visible",
    )
    claim = options[selected_label]

    st.divider()
    st.caption(f"Modèle : `{os.environ.get('MODEL_ID', 'us.anthropic.claude-sonnet-4-6')}`")
    st.caption(f"Région : `{os.environ.get('AWS_REGION', 'eu-west-1')}`")


# ---------------------------------------------------------------------------
# Layout principal : colonne gauche (détails) | colonne droite (IA)
# ---------------------------------------------------------------------------

col_left, col_right = st.columns([3, 2], gap="large")

# ── Colonne gauche : détails de la réclamation ──────────────────────────────

with col_left:

    # Détails
    st.markdown('<p class="section-title">Détails de la réclamation</p>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="claim-card">
        <b>ID</b> &nbsp; <code>{claim.id}</code><br>
        <b>Client</b> &nbsp; {claim.code_client or "—"}<br>
        <b>Type de produit</b> &nbsp; {claim.type_produit or "—"}<br>
        <b>N° commande</b> &nbsp; {claim.num_commande or "—"}<br>
        <b>Repères</b> &nbsp; {claim.reperes or "—"}
    </div>
    """, unsafe_allow_html=True)

    # ── Galerie d'images ──────────────────────────────────────────────────────

    if claim.attachments:
        st.markdown('<p class="section-title">📸 Images associées</p>', unsafe_allow_html=True)
        
        # Filtrer uniquement les images
        image_files = [f for f in claim.attachments 
                      if Path(f).suffix.lower() in ('.jpg', '.jpeg', '.png')]
        
        if image_files:
            # Afficher en galerie (max 3 colonnes)
            cols = st.columns(min(len(image_files), 3))
            for i, filename in enumerate(image_files):
                file_path = ATTACHMENTS_DIR / filename
                with cols[i % len(cols)]:
                    try:
                        st.image(str(file_path), caption=filename, use_container_width=True)
                    except Exception as e:
                        st.warning(f"Erreur image `{filename}` : {e}")
        
        # PDFs séparément
        pdf_files = [f for f in claim.attachments 
                    if Path(f).suffix.lower() == '.pdf']
        if pdf_files:
            st.markdown('<p class="section-title">📄 Documents PDF</p>', unsafe_allow_html=True)
            for filename in pdf_files:
                file_path = ATTACHMENTS_DIR / filename
                if file_path.exists():
                    with open(file_path, "rb") as f:
                        pdf_bytes = f.read()
                    st.download_button(
                        label=f"📄 Télécharger {filename}",
                        data=pdf_bytes,
                        file_name=filename,
                        mime="application/pdf",
                    )
                else:
                    st.warning(f"PDF introuvable : `{filename}`")

    st.markdown("**📝 Description**")
    st.markdown(
        f'<div style="background:#fff;border:1px solid #ddd;border-radius:6px;'
        f'padding:0.9rem 1rem;font-size:0.97rem;line-height:1.6;">'
        f'{claim.description}</div>',
        unsafe_allow_html=True,
    )

    if claim.souhait:
        st.markdown("**💬 Souhait client**")
        st.info(claim.souhait)

    # Labels de référence (week13)
    if any([claim.ref_type_litige, claim.ref_responsabilite,
            claim.ref_solution, claim.ref_precision_produit]):
        with st.expander("📌 Labels de référence (humain)", expanded=False):
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Type litige",      claim.ref_type_litige      or "—")
            r2.metric("Responsabilité",   claim.ref_responsabilite   or "—")
            r3.metric("Solution",         claim.ref_solution         or "—")
            r4.metric("Précision produit",claim.ref_precision_produit or "—")


# ── Colonne droite : analyse IA ──────────────────────────────────────────────

with col_right:
    st.markdown('<p class="section-title">🤖 Analyse IA</p>', unsafe_allow_html=True)

    # Bouton d'analyse
    run_analysis = st.button(
        "🚀 Lancer l'analyse IA",
        type="primary",
        use_container_width=True,
    )

    # Clé de session pour stocker le résultat par réclamation
    result_key = f"result_{claim.id}"

    if run_analysis:
        from src.image_loader import resolve_attachments

        with st.spinner("Analyse en cours…"):
            try:
                classifier = get_classifier()
                attachments = resolve_attachments(claim.attachments, ATTACHMENTS_DIR)
                result = classifier.classify(claim, attachments)
                st.session_state[result_key] = result
            except Exception as exc:
                st.error(f"❌ Erreur lors de l'analyse : {exc}")
                st.session_state.pop(result_key, None)

    # Affichage du résultat
    result = st.session_state.get(result_key)

    if result is not None:
        if result.error:
            st.error(f"❌ Erreur Bedrock : {result.error}")
        else:
            st.success("✅ Analyse terminée avec succès")
            st.divider()

            # Cards des 4 champs
            fields = [
                ("⚖️ Type de litige",    result.type_litige,       claim.ref_type_litige),
                ("👤 Responsabilité",    result.responsabilite,    claim.ref_responsabilite),
                ("🔧 Solution",          result.solution,          claim.ref_solution),
                ("🔩 Précision produit", result.precision_produit, claim.ref_precision_produit),
            ]

            for label, value, ref in fields:
                match = ""
                if ref:
                    icon = "✅" if value.lower() == ref.lower() else "❌"
                    match = f'<div class="ref-badge">{icon} Référence : {ref}</div>'

                st.markdown(f"""
                <div class="result-card">
                    <div class="result-label">{label}</div>
                    <div class="result-value">{value}</div>
                    {match}
                </div>
                """, unsafe_allow_html=True)
                st.write("")  # espacement

    else:
        st.markdown("""
        <div style="text-align:center;color:#aaa;padding:3rem 1rem;">
            <div style="font-size:2.5rem;">🤖</div>
            <div style="margin-top:0.5rem;font-size:0.9rem;">
                Cliquez sur <b>Lancer l'analyse IA</b><br>pour classifier cette réclamation.
            </div>
        </div>
        """, unsafe_allow_html=True)
