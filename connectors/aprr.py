"""
Connecteur APRR (péages)
─────────────────────────
Variables d'environnement Railway :
  APRR_LOGIN    → votre email ou identifiant
  APRR_PASSWORD → votre mot de passe
"""

import os
import uuid
import time
from playwright.sync_api import sync_playwright

UPLOAD_FOLDER = "uploads"

def collect_aprr(log):
    login = os.getenv("APRR_LOGIN")
    password = os.getenv("APRR_PASSWORD")

    if not login or not password:
        raise ValueError("APRR_LOGIN ou APRR_PASSWORD manquant dans les variables d'environnement")

    invoices = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            log("   APRR : ouverture de la page de connexion...")
            page.goto("https://www.aprr.fr/fr/mon-compte/connexion", timeout=30000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            # Accepter les cookies si la bannière apparaît
            try:
                page.click('button:has-text("Accepter"), button:has-text("Tout accepter")', timeout=3000)
            except Exception:
                pass

            # Connexion
            page.fill('input[type="email"], input[name*="login"], input[id*="login"]', login)
            page.fill('input[type="password"]', password)
            page.click('button[type="submit"], input[type="submit"]')
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            log("   APRR : navigation vers les relevés...")
            page.goto("https://www.aprr.fr/fr/mon-compte/mes-releves", timeout=30000)
            page.wait_for_load_state("networkidle")

            # Liens PDF (à ajuster selon la structure réelle du site APRR)
            pdf_links = page.query_selector_all('a[href*=".pdf"], a[href*="releve"], a[href*="facture"]')
            log(f"   APRR : {len(pdf_links)} relevé(s) détecté(s)")

            for link in pdf_links[:12]:
                href = link.get_attribute("href")
                text = link.inner_text().strip() or "releve_aprr.pdf"
                if not href:
                    continue

                if not href.startswith("http"):
                    href = "https://www.aprr.fr" + href

                inv_id = str(uuid.uuid4())[:8]
                filename = f"aprr_{inv_id}.pdf"
                path = os.path.join(UPLOAD_FOLDER, filename)

                response = page.request.get(href)
                with open(path, "wb") as f:
                    f.write(response.body())

                invoices.append({
                    "id": inv_id,
                    "name": text or filename,
                    "date": "—",
                    "amount": "—",
                    "source": "aprr",
                    "path": path,
                    "selected": True,
                })
                log(f"   📄 {text}")

        except Exception as e:
            browser.close()
            raise e

        browser.close()

    return invoices
