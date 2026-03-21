import os
import base64
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def get_gmail_send_service():
    creds = None
    gmail_token = os.getenv("GMAIL_TOKEN")
    if gmail_token:
        import json
        creds = Credentials.from_authorized_user_info(json.loads(gmail_token), SCOPES)
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)

def send_to_pennylane(invoices, log):
    pennylane_email = os.getenv("PENNYLANE_EMAIL")
    smtp_email = os.getenv("SMTP_EMAIL")

    if not all([pennylane_email, smtp_email]):
        raise ValueError("Variables manquantes : PENNYLANE_EMAIL et/ou SMTP_EMAIL")

    log(f"📤 Envoi de {len(invoices)} facture(s) vers Pennylane...")
    log(f"   Expéditeur : {smtp_email}")
    log(f"   Destinataire : {pennylane_email}")

    batches = _batch_invoices(invoices, max_size_mb=20)
    log(f"   {len(batches)} email(s) à envoyer")

    service = get_gmail_send_service()
    sent_count = 0
    errors = []

    for i, batch in enumerate(batches, 1):
        try:
            _send_email_batch(service, smtp_email, pennylane_email, batch, i, len(batches), log)
            sent_count += len(batch)
            for inv in batch:
                log(f"   ✅ {inv['name']}")
        except Exception as e:
            errors.append(str(e))
            log(f"   ❌ Erreur batch {i} : {e}")
            log(f"   ❌ Détail : {traceback.format_exc()}")

    log("")
    log(f"📊 Résumé : {sent_count}/{len(invoices)} facture(s) envoyée(s) à Pennylane")
    if errors:
        log(f"   ⚠️  {len(errors)} erreur(s) : {'; '.join(errors)}")
    else:
        log("   Votre comptable peut maintenant accéder aux factures sur Pennylane.")


def _send_email_batch(service, smtp_email, to, batch, batch_num, total_batches, log):
    msg = MIMEMultipart()
    msg["From"] = smtp_email
    msg["To"] = to
    date_str = datetime.now().strftime("%d/%m/%Y")
    suffix = f" ({batch_num}/{total_batches})" if total_batches > 1 else ""
    msg["Subject"] = f"Factures {date_str}{suffix}"

    sources = sorted({inv["source"].capitalize() for inv in batch})
    body = (
        f"Bonjour,\n\n"
        f"Veuillez trouver ci-joint {len(batch)} facture(s) collectées automatiquement "
        f"le {date_str}.\n\n"
        f"Sources : {', '.join(sources)}\n\n"
        f"Factures :\n"
    )
    for inv in batch:
        body += f"  • {inv['name']} — {inv['source'].capitalize()} — {inv['date']}\n"
    body += "\nCordialement"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for inv in batch:
        path = inv.get("path")
        if not path or not os.path.exists(path):
            log(f"   ⚠️  Fichier introuvable : {path}")
            continue
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        safe_name = inv["name"] if inv["name"].endswith(".pdf") else inv["name"] + ".pdf"
        part.add_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        msg.attach(part)

    log(f"   Envoi via API Gmail...")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    log(f"   Email {batch_num}/{total_batches} envoyé ✓")


def _batch_invoices(invoices, max_size_mb=20):
    max_bytes = max_size_mb * 1024 * 1024
    batches = []
    current_batch = []
    current_size = 0
    for inv in invoices:
        path = inv.get("path", "")
        size = os.path.getsize(path) if path and os.path.exists(path) else 0
        if current_batch and current_size + size > max_bytes:
            batches.append(current_batch)
            current_batch = []
            current_size = 0
        current_batch.append(inv)
        current_size += size
    if current_batch:
        batches.append(current_batch)
    return batches