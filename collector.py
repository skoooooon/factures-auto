import os
from connectors.gmail import collect_gmail
from connectors.total import collect_total
from connectors.aprr import collect_aprr
from connectors.easyjet import collect_easyjet
# Ajoutez vos connecteurs ici au fur et à mesure

def run_collection(state, log):
    """
    Orchestre la collecte depuis toutes les sources.
    Priorité : Gmail d'abord, puis scraping pour les manquants.
    """
    log("🚀 Démarrage de la collecte...")
    os.makedirs("uploads", exist_ok=True)

    # ── 1. Gmail ──────────────────────────────────────────────
    log("📧 Scan de Gmail...")
    try:
        gmail_invoices = collect_gmail(log, days_back=365)
        for inv in gmail_invoices:
            state["invoices"].append(inv)
        log(f"✅ Gmail : {len(gmail_invoices)} facture(s) trouvée(s)")
    except Exception as e:
        log(f"❌ Gmail : erreur — {e}")
        gmail_invoices = []

    # Sources déjà couvertes par Gmail (basé sur le champ "source")
    covered_sources = {inv["source"] for inv in state["invoices"]}
    log(f"   Sources déjà couvertes : {covered_sources or 'aucune'}")

    # ── 2. Connecteurs scraping ───────────────────────────────
    scraping_connectors = [
        ("Total",   collect_total,   "total"),
        ("APRR",    collect_aprr,    "aprr"),
        ("EasyJet", collect_easyjet, "easyjet"),
        # ("Amazon",  collect_amazon,  "amazon"),
        # ("Orange",  collect_orange,  "orange"),
    ]

    for name, connector_fn, source_key in scraping_connectors:
        if source_key in covered_sources:
            log(f"⏭️  {name} : déjà récupéré via Gmail, ignoré")
            continue
        log(f"🔍 {name} : connexion à l'espace client...")
        try:
            invoices = connector_fn(log)
            for inv in invoices:
                state["invoices"].append(inv)
            log(f"✅ {name} : {len(invoices)} facture(s) récupérée(s)")
        except Exception as e:
            log(f"❌ {name} : erreur — {e}")

    # ── 3. Résumé ─────────────────────────────────────────────
    total = len(state["invoices"])
    log(f"")
    log(f"📊 Collecte terminée : {total} facture(s) au total")
    log(f"   Vérifiez la liste et cliquez sur Envoyer quand vous êtes prêt.")
