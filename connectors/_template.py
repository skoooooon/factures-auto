"""
Template pour ajouter un nouveau connecteur
─────────────────────────────────────────────
Copiez ce fichier, renommez-le (ex: amazon.py), et adaptez les sélecteurs.
Ajoutez ensuite le connecteur dans collector.py.

Variables d'environnement à créer sur Railway :
  MONSERVICE_LOGIN    → identifiant
  MONSERVICE_PASSWORD → mot de passe
"""

import os
import uuid
import time
from playwright.sync_api import sync_playwright

UPLOAD_FOLDER = "uploads"

def collect_template(log):
    login = os.getenv("MONSERVICE_LOGIN")
    password = os.getenv("MONSERVICE_PASSWORD")

    if not login or not password:
        raise ValueError("MONSERVICE_LOGIN ou MONSERVICE_PASSWORD manquant")

    invoices = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # ── 1. Connexion ──────────────────────────────────────
            log("   MonService : connexion...")
            page.goto("https://www.monservice.fr/connexion", timeout=30000)
            page.wait_for_load_state("networkidle")

            # Accepter cookies (optionnel)
            try:
                page.click('button:has-text("Accepter")', timeout=2000)
            except Exception:
                pass

            page.fill('input[type="email"]', login)
            page.fill('input[type="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # ── 2. Navigation vers les factures ───────────────────
            log("   MonService : recherche des factures...")
            page.goto("https://www.monservice.fr/mon-compte/factures", timeout=30000)
            page.wait_for_load_state("networkidle")

            # ── 3. Téléchargement ─────────────────────────────────
            # Adaptez ce sélecteur selon la structure HTML du site
            pdf_links = page.query_selector_all('a[href*=".pdf"]')

            for link in pdf_links[:12]:
                href = link.get_attribute("href")
                text = link.inner_text().strip() or "facture.pdf"
                if not href:
                    continue

                inv_id = str(uuid.uuid4())[:8]
                filename = f"monservice_{inv_id}.pdf"
                path = os.path.join(UPLOAD_FOLDER, filename)

                response = page.request.get(href)
                with open(path, "wb") as f:
                    f.write(response.body())

                invoices.append({
                    "id": inv_id,
                    "name": text,
                    "date": "—",   # À extraire si possible
                    "amount": "—", # À extraire si possible
                    "source": "monservice",
                    "path": path,
                    "selected": True,
                })
                log(f"   📄 {text}")

        except Exception as e:
            browser.close()
            raise e

        browser.close()

    return invoices
