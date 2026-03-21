"""
Connecteur dynamique — exécute le scraping basé sur la config JSON.
"""

import os
import uuid
import time
from playwright.sync_api import sync_playwright

UPLOAD_FOLDER = "uploads"

def collect_dynamic(connector, log):
    name = connector["name"]
    slug = connector["slug"]
    login_url = connector["login_url"]
    invoices_url = connector["invoices_url"]
    css_selector = connector["css_selector"]
    login = connector["login"]
    password = connector["password"]

    invoices = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # ── Connexion ──────────────────────────────────────
            log(f"   {name} : ouverture de {login_url}...")
            page.goto(login_url, timeout=30000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            # Accepter cookies si présent
            try:
                page.click('button:has-text("Accepter"), button:has-text("Tout accepter"), #onetrust-accept-btn-handler', timeout=3000)
                time.sleep(1)
            except Exception:
                pass

            # Remplir le formulaire de connexion
            try:
                page.fill('input[type="email"]', login)
            except Exception:
                try:
                    page.fill('input[name*="login"], input[name*="email"], input[id*="login"], input[id*="email"]', login)
                except Exception:
                    pass

            try:
                page.fill('input[type="password"]', password)
            except Exception:
                pass

            page.click('button[type="submit"], input[type="submit"]')
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # ── Navigation vers les factures ───────────────────
            log(f"   {name} : navigation vers {invoices_url}...")
            page.goto(invoices_url, timeout=30000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            # ── Récupération des PDFs ──────────────────────────
            links = page.query_selector_all(css_selector)
            log(f"   {name} : {len(links)} lien(s) détecté(s)")

            for link in links[:12]:
                href = link.get_attribute("href") or ""
                text = link.inner_text().strip() or f"{slug}.pdf"

                if not href:
                    continue
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(invoices_url, href)

                inv_id = str(uuid.uuid4())[:8]
                filename = f"{slug}_{inv_id}.pdf"
                path = os.path.join(UPLOAD_FOLDER, filename)

                try:
                    with page.expect_download(timeout=10000) as dl_info:
                        page.goto(href)
                    dl_info.value.save_as(path)
                except Exception:
                    try:
                        response = page.request.get(href)
                        with open(path, "wb") as f:
                            f.write(response.body())
                    except Exception as e:
                        log(f"   ⚠️  Impossible de télécharger {text} : {e}")
                        continue

                invoices.append({
                    "id": inv_id,
                    "name": text if text.endswith(".pdf") else text + ".pdf",
                    "date": "—",
                    "amount": "—",
                    "source": slug,
                    "path": path,
                    "selected": True,
                })
                log(f"   📄 {text}")

        except Exception as e:
            context.close()
            browser.close()
            raise e

        context.close()
        browser.close()

    return invoices