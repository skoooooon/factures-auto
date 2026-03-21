import os
import json
from connectors.gmail import collect_gmail
from connectors.total import collect_total
from connectors.aprr import collect_aprr
from connectors.easyjet import collect_easyjet
from connectors.dynamic import collect_dynamic

CONNECTORS_FILE = "connectors_config.json"

def load_dynamic_connectors():
    if os.path.exists(CONNECTORS_FILE):
        with open(CONNECTORS_FILE, "r") as f:
            return json.load(f)
    return []

def run_collection(state, log):
    log("🚀 Démarrage de la collecte...")
    os.makedirs("uploads", exist_ok=True)

    # ── 1. Gmail ──────────────────────────────────────────────
    log("📧 Scan de Gmail...")
    try:
        gmail_invoices = collect_gmail(log, days_back=21)
        for inv in gmail_invoices:
            state["invoices"].append(inv)
        log(f"✅ Gmail : {len(gmail_invoices)} facture(s) trouvée(s)")
    except Exception as e:
        log(f"❌ Gmail : erreur — {e}")
        gmail_invoices = []

    covered_sources = {inv["source"] for inv in state["invoices"]}
    log(f"   Sources couvertes par Gmail : {covered_sources or 'aucune'}")

    # ── 2. Connecteurs statiques ───────────────────────────────
    static_connectors = [
        ("Total",   collect_total,   "total"),
        ("APRR",    collect_aprr,    "aprr"),
        ("EasyJet", collect_easyjet, "easyjet"),
    ]

    for name, connector_fn, source_key in static_connectors:
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

    # ── 3. Connecteurs dynamiques ──────────────────────────────
    dynamic_connectors = load_dynamic_connectors()
    enabled = [c for c in dynamic_connectors if c.get("enabled", True)]

    if enabled:
        log(f"🔌 {len(enabled)} connecteur(s) dynamique(s) à interroger...")
    for connector in enabled:
        slug = connector["slug"]
        name = connector["name"]
        if slug in covered_sources:
            log(f"⏭️  {name} : déjà récupéré via Gmail, ignoré")
            continue
        log(f"🔍 {name} : connexion à l'espace client...")
        try:
            invoices = collect_dynamic(connector, log)
            for inv in invoices:
                state["invoices"].append(inv)
            log(f"✅ {name} : {len(invoices)} facture(s) récupérée(s)")
        except Exception as e:
            log(f"❌ {name} : erreur — {e}")

    # ── 4. Résumé ──────────────────────────────────────────────
    total = len(state["invoices"])
    log(f"")
    log(f"📊 Collecte terminée : {total} facture(s) au total")
    log(f"   Vérifiez la liste et cliquez sur Envoyer quand vous êtes prêt.")