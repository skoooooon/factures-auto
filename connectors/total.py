"""
Connecteur Total Energies
──────────────────────────
Variables d'environnement Railway :
  TOTAL_LOGIN    → votre email de connexion
  TOTAL_PASSWORD → votre mot de passe

Note : si la 2FA est activée sur votre compte Total, désactivez-la
ou contactez-moi pour implémenter la gestion TOTP.
"""

import os
import uuid
import time
from playwright.sync_api import sync_playwright

UPLOAD_FOLDER = "uploads"

def collect_total(log):
    login = os.getenv("TOTAL_LOGIN")
    password = os.getenv("TOTAL_PASSWORD")

    if not login or not password:
        raise ValueError("TOTAL_LOGIN ou TOTAL_PASSWORD manquant dans les variables d'environnement")

    invoices = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            log("   Total : ouverture de la page de connexion...")
            page.goto("https://particuliers.totalenergies.fr/mon-espace-client/connexion", timeout=30000)
            page.wait_for_load_state("networkidle")

            # Connexion
            page.fill('input[type="email"], input[name*="email"], input[name*="login"]', login)
            page.fill('input[type="password"]', password)
            page.click('button[type="submit"], input[type="submit"]')
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            log("   Total : navigation vers les factures...")
            # Adapter l'URL selon la structure réelle du site
            page.goto("https://particuliers.totalenergies.fr/mon-espace-client/mes-factures", timeout=30000)
            page.wait_for_load_state("networkidle")

            # Récupération des liens PDF
            # ⚠️ Les sélecteurs ci-dessous sont indicatifs — à ajuster selon le site réel
            pdf_links = page.query_selector_all('a[href*=".pdf"], a[href*="facture"], a[download]')
            log(f"   Total : {len(pdf_links)} lien(s) PDF détecté(s)")

            for link in pdf_links[:12]:  # Max 12 factures (1 an)
                href = link.get_attribute("href")
                text = link.inner_text().strip() or "facture_total.pdf"
                if not href:
                    continue

                if not href.startswith("http"):
                    href = "https://particuliers.totalenergies.fr" + href

                # Téléchargement
                inv_id = str(uuid.uuid4())[:8]
                filename = f"total_{inv_id}.pdf"
                path = os.path.join(UPLOAD_FOLDER, filename)

                with page.expect_download() as download_info:
                    page.goto(href)
                download = download_info.value
                download.save_as(path)

                invoices.append({
                    "id": inv_id,
                    "name": text or filename,
                    "date": "—",
                    "amount": "—",
                    "source": "total",
                    "path": path,
                    "selected": True,
                })
                log(f"   📄 {text}")

        except Exception as e:
            browser.close()
            raise e

        browser.close()

    return invoices
