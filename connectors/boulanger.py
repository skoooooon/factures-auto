"""
Connecteur Boulanger
─────────────────────
Variables d'environnement Railway :
  BOULANGER_LOGIN    → votre email
  BOULANGER_PASSWORD → votre mot de passe
"""

import os
import uuid
import time
import requests
from playwright.sync_api import sync_playwright

UPLOAD_FOLDER = "uploads"
API_BASE = "https://api.boulanger.com"

def collect_boulanger(log):
    login = os.getenv("BOULANGER_LOGIN")
    password = os.getenv("BOULANGER_PASSWORD")

    if not login or not password:
        raise ValueError("BOULANGER_LOGIN ou BOULANGER_PASSWORD manquant")

    invoices = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        token = None

        def intercept(request):
            nonlocal token
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer ") and len(auth) > 50:
                token = auth.replace("Bearer ", "")

        page.on("request", intercept)

        try:
            log("   Boulanger : ouverture de la page de connexion...")
            page.goto("https://www.boulanger.com/se-connecter", timeout=30000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            try:
                page.click('#popin_tc_privacy_button_2, button:has-text("Tout accepter")', timeout=3000)
                time.sleep(1)
            except Exception:
                pass

            page.fill('input[type="email"], input[name*="email"], input[id*="email"]', login)
            page.fill('input[type="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            log("   Boulanger : navigation vers les commandes...")
            page.goto("https://www.boulanger.com/mon-compte/mes-commandes", timeout=30000)
            page.wait_for_load_state("networkidle")
            time.sleep(3)

            if not token:
                raise ValueError("Token Bearer non capturé — vérifiez les identifiants")

            log(f"   Boulanger : token récupéré ✓")

            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Origin": "https://www.boulanger.com",
                "Referer": "https://www.boulanger.com/",
            }

            log("   Boulanger : récupération des commandes...")
            orders_res = requests.get(
                f"{API_BASE}/orders-v1/orders?limit=50",
                headers=headers,
                timeout=15
            )

            if not orders_res.ok:
                raise ValueError(f"API commandes : {orders_res.status_code}")

            orders = orders_res.json()
            order_list = orders.get("orders", orders) if isinstance(orders, dict) else orders
            log(f"   Boulanger : {len(order_list)} commande(s) trouvée(s)")

            for order in order_list:
                order_id = order.get("id") or order.get("orderNumber") or order.get("number")
                if not order_id:
                    continue

                invoice_url = f"{API_BASE}/documents/invoice-v1/invoice/{order_id}"
                pdf_res = requests.get(invoice_url, headers=headers, timeout=15)

                if not pdf_res.ok or "pdf" not in pdf_res.headers.get("content-type", "").lower():
                    log(f"   ⏭️  Commande {order_id} : pas de facture PDF")
                    continue

                inv_id = str(uuid.uuid4())[:8]
                filename = f"boulanger_{order_id}.pdf"
                path = os.path.join(UPLOAD_FOLDER, filename)

                with open(path, "wb") as f:
                    f.write(pdf_res.content)

                date = order.get("date", "—")[:10] if order.get("date") else "—"
                amount = str(order.get("totalAmount", "—"))

                invoices.append({
                    "id": inv_id,
                    "name": filename,
                    "date": date,
                    "amount": amount,
                    "source": "boulanger",
                    "path": path,
                    "selected": True,
                })
                log(f"   📄 {filename}")

        except Exception as e:
            context.close()
            browser.close()
            raise e

        context.close()
        browser.close()

    return invoices