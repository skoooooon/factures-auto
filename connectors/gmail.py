"""
Connecteur Gmail
────────────────
Prérequis :
  1. Créer un projet sur https://console.cloud.google.com
  2. Activer l'API Gmail
  3. Créer des identifiants OAuth 2.0 (type "Application de bureau")
  4. Télécharger credentials.json et le placer à la racine du projet
  5. Au premier lancement, une fenêtre navigateur s'ouvre pour autoriser l'accès
     → un fichier token.json est créé automatiquement pour les fois suivantes

Variables d'environnement Railway nécessaires : aucune (OAuth gère l'auth)
"""

import os
import base64
import uuid
import re
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
UPLOAD_FOLDER = "uploads"

# Mots-clés pour détecter les emails de facturation
INVOICE_KEYWORDS = [
    "facture", "invoice", "reçu", "receipt", "confirmation de paiement",
    "votre commande", "your order", "ticket", "justificatif",
    "votre facture", "avis d'échéance", "quittance",
    "order confirmation", "your invoice", "payment confirmation",
]

# Mots-clés à exclure dans l'objet
EXCLUDE_KEYWORDS = [
    "relevé", "releve", "statement", "avis de virement",
    "avis de prélèvement", "votre virement", "notification",
    "alerte", "information", "newsletter", "confirmation de connexion",
]

# Expéditeurs bancaires à exclure
EXCLUDE_SENDERS = [

]

def get_gmail_service():
    creds = None
    
    # Sur Railway : token stocké en variable d'environnement
    gmail_token = os.getenv("GMAIL_TOKEN")
    if gmail_token:
        import json
        creds = Credentials.from_authorized_user_info(json.loads(gmail_token), SCOPES)
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    
    return build("gmail", "v1", credentials=creds)

def collect_gmail(log, days_back=60):
    """
    Scanne les X derniers jours de Gmail et récupère les PDFs de facturation.
    """
    service = get_gmail_service()
    invoices = []

    # Requête Gmail : emails avec pièces jointes PDF des X derniers jours
    after_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
    query = f"has:attachment filename:pdf after:{after_date}"

    log(f"   Recherche : {query}")

    # Pagination pour récupérer tous les résultats (pas de limite à 100)
    messages = []
    page_token = None
    while True:
        params = {"userId": "me", "q": query, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        results = service.users().messages().list(**params).execute()
        messages.extend(results.get("messages", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    log(f"   {len(messages)} email(s) avec PDF trouvés")

    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        subject = _get_header(msg, "Subject") or "Sans objet"
        date_str = _get_header(msg, "Date") or ""
        sender = _get_header(msg, "From") or ""

        # Filtre : est-ce une facture ?
        if not _is_invoice(subject, sender):
            continue

        # Récupère les pièces jointes PDF
        parts = msg.get("payload", {}).get("parts", [])
        for part in parts:
            mime = part.get("mimeType", "")
            filename = part.get("filename", "")
            if "pdf" not in mime.lower() and not filename.lower().endswith(".pdf"):
                continue

            filename = part.get("filename", "facture.pdf")
            attachment_id = part.get("body", {}).get("attachmentId")
            if not attachment_id:
                continue

            # Téléchargement
            attachment = service.users().messages().attachments().get(
                userId="me", messageId=msg_ref["id"], id=attachment_id
            ).execute()
            data = base64.urlsafe_b64decode(attachment["data"])

            # Sauvegarde
            inv_id = str(uuid.uuid4())[:8]
            safe_name = f"gmail_{inv_id}_{filename}"
            path = os.path.join(UPLOAD_FOLDER, safe_name)
            with open(path, "wb") as f:
                f.write(data)

            # Détection de la source
            source = _detect_source(sender)

            invoices.append({
                "id": inv_id,
                "name": filename,
                "date": _parse_date(date_str),
                "amount": "—",
                "source": source,
                "sender": sender,
                "path": path,
                "selected": True,
            })
            log(f"   📎 {filename} ({sender})")

    return invoices

def _get_header(msg, name):
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return None

def _is_invoice(subject, sender):
    text = (subject + " " + sender).lower()
    # Exclure les expéditeurs bancaires
    if any(ex in text for ex in EXCLUDE_SENDERS):
        return False
    # Exclure les objets non liés aux factures
    if any(ex in subject.lower() for ex in EXCLUDE_KEYWORDS):
        return False
    # Doit contenir un mot-clé de facturation
    return any(kw in text for kw in INVOICE_KEYWORDS)

def _detect_source(sender):
    sender_lower = sender.lower()
    sources = {
        "total": "total",
        "totalenergies": "total",
        "aprr": "aprr",
        "easyjet": "easyjet",
        "amazon": "amazon",
        "orange": "orange",
        "sfr": "sfr",
        "bouygues": "bouygues",
        "boulanger": "boulanger",
    }
    for key, val in sources.items():
        if key in sender_lower:
            return val
    return "gmail"

def _parse_date(date_str):
    """Tente de parser la date de l'email en format lisible."""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return date_str[:10] if date_str else "—"