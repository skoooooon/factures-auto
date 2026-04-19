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
import unicodedata
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
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
    "societegenerale", "bnpparibas", "creditmutuel", "lcl.fr",
    "caisse-epargne", "labanquepostale", "boursorama", "fortuneo",
    "ing.fr", "hsbc", "cic.fr", "bred.fr", "credit-agricole",
]

def get_gmail_service():
    creds = None
    
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

def _sanitize_filename(filename, fallback):
    """Nettoie le nom de fichier en supprimant les caractères spéciaux."""
    if not filename or not filename.strip():
        return fallback
    # Normalisation unicode + suppression des caractères non-ASCII
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")
    # Garder uniquement les caractères sûrs
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
    filename = filename.strip()
    if not filename:
        return fallback
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    return filename

def collect_gmail(log, date_from=None, date_to=None, days_back=60):
    service = get_gmail_service()
    invoices = []

    if date_from and date_to:
        after_date = date_from.strftime("%Y/%m/%d")
        before_date = date_to.strftime("%Y/%m/%d")
        query = f"has:attachment filename:pdf after:{after_date} before:{before_date} -in:sent"
    else:
        from datetime import timedelta
        after_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
        query = f"has:attachment filename:pdf after:{after_date} -in:sent"

    log(f"   Recherche : {query}")

    # Pagination pour récupérer tous les résultats
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

        if not _is_invoice(subject, sender):
            continue

        parts = msg.get("payload", {}).get("parts", [])
        for part in parts:
            mime = part.get("mimeType", "")
            raw_filename = part.get("filename", "")

            if "pdf" not in mime.lower() and not raw_filename.lower().endswith(".pdf"):
                continue

            attachment_id = part.get("body", {}).get("attachmentId")
            if not attachment_id:
                continue

            # Nettoyage du nom de fichier
            date_label = _parse_date(date_str).replace("/", "-")
            fallback = f"facture_{date_label}.pdf"
            filename = _sanitize_filename(raw_filename, fallback)

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
    if any(ex in text for ex in EXCLUDE_SENDERS):
        return False
    if any(ex in subject.lower() for ex in EXCLUDE_KEYWORDS):
        return False
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
        "lidl": "lidl",
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