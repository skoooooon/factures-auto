"""
Connecteur EasyJet
───────────────────
Variables d'environnement Railway :
  EASYJET_LOGIN    → votre email
  EASYJET_PASSWORD → votre mot de passe

Note : EasyJet peut déclencher une vérification anti-bot (Cloudflare).
Si le connecteur échoue, les factures EasyJet arrivent généralement
par email — Gmail les récupérera automatiquement.
"""

import os
import uuid
import time
from playwright.sync_api import sync_playwright

UPLOAD_FOLDER = "uploads"

def collect_easyjet(log):
    login = os.getenv("EASYJET_LOGIN")
    password = os.getenv("EASYJET_PASSWORD")

    if not login or not password:
        raise ValueError("EASYJET_LOGIN ou EASYJET_PASSWORD manquant dans les variables d'environnement")

    invoices = []

    with sync_playwright() as p:
        # User-agent réaliste pour réduire le risque de blocage
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            log("   EasyJet : ouverture de la page de connexion...")
            page.goto("https://www.easyjet.com/fr/connexion", timeout=30000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # Accepter les cookies
            try:
                page.click('button:has-text("Accepter"), #onetrust-accept-btn-handler', timeout=3000)
                time.sleep(1)
            except Exception:
                pass

            # Connexion
            page.fill('input[type="email"], input[name="LoginEmail"]', login)
            page.fill('input[type="password"], input[name="Password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")
            time.sleep(3)

            log("   EasyJet : navigation vers l'historique des vols...")
            page.goto("https://www.easyjet.com/fr/myeasyjet/bookings", timeout=30000)
            page.wait_for_load_state("networkidle")

            # EasyJet: cherche les liens de reçus/confirmations
            pdf_links = page.query_selector_all(
                'a[href*="receipt"], a[href*="confirmation"], a[href*=".pdf"], a:has-text("Reçu"), a:has-text("Télécharger")'
            )
            log(f"   EasyJet : {len(pdf_links)} document(s) détecté(s)")

            for link in pdf_links[:12]:
                href = link.get_attribute("href")
                text = link.inner_text().strip() or "easyjet.pdf"
                if not href:
                    continue

                if not href.startswith("http"):
                    href = "https://www.easyjet.com" + href

                inv_id = str(uuid.uuid4())[:8]
                filename = f"easyjet_{inv_id}.pdf"
                path = os.path.join(UPLOAD_FOLDER, filename)

                try:
                    with page.expect_download(timeout=10000) as dl_info:
                        page.goto(href)
                    dl_info.value.save_as(path)
                except Exception:
                    response = page.request.get(href)
                    with open(path, "wb") as f:
                        f.write(response.body())

                invoices.append({
                    "id": inv_id,
                    "name": text or filename,
                    "date": "—",
                    "amount": "—",
                    "source": "easyjet",
                    "path": path,
                    "selected": True,
                })
                log(f"   📄 {text}")

        except Exception as e:
            browser.close()
            raise e

        context.close()
        browser.close()

    return invoices
