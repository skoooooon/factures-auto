import os
import json
import threading
import uuid
from flask import Flask, render_template, jsonify, request, send_from_directory
from collector import run_collection
from sender import send_to_pennylane
from functools import wraps
from flask import session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "changez-moi")
app.config["UPLOAD_FOLDER"] = "uploads"

CONNECTORS_FILE = "connectors_config.json"

def load_connectors():
    if os.path.exists(CONNECTORS_FILE):
        with open(CONNECTORS_FILE, "r") as f:
            return json.load(f)
    return []

def save_connectors(connectors):
    with open(CONNECTORS_FILE, "w") as f:
        json.dump(connectors, f, indent=2, ensure_ascii=False)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# État partagé entre les threads
state = {
    "collecting": False,
    "sending": False,
    "logs": [],
    "invoices": [],
}

def log(msg):
    state["logs"].append(msg)
    print(msg)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == os.getenv("APP_PASSWORD", "changez-moi"):
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "Mot de passe incorrect"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/api/collect", methods=["POST"])
@login_required
def collect():
    if state["collecting"]:
        return jsonify({"error": "Collecte déjà en cours"}), 400

    data = request.get_json() or {}
    month = data.get("month")
    year = data.get("year")

    state["collecting"] = True
    state["logs"] = []
    state["invoices"] = []

    def run():
        try:
            run_collection(state, log, month=month, year=year)
        finally:
            state["collecting"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/api/send", methods=["POST"])
@login_required
def send():
    if state["sending"]:
        return jsonify({"error": "Envoi déjà en cours"}), 400
    selected = [inv for inv in state["invoices"] if inv.get("selected", True)]
    if not selected:
        return jsonify({"error": "Aucune facture sélectionnée"}), 400

    state["sending"] = True
    state["logs"] = []

    def run():
        try:
            send_to_pennylane(selected, log)
        finally:
            state["sending"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/api/status")
@login_required
def status():
    return jsonify({
        "collecting": state["collecting"],
        "sending": state["sending"],
        "logs": state["logs"][-50:],
        "invoices": state["invoices"],
    })

@app.route("/api/invoices/<invoice_id>/toggle", methods=["POST"])
@login_required
def toggle_invoice(invoice_id):
    for inv in state["invoices"]:
        if inv["id"] == invoice_id:
            inv["selected"] = not inv.get("selected", True)
            return jsonify(inv)
    return jsonify({"error": "Facture introuvable"}), 404

@app.route("/api/invoices/<invoice_id>", methods=["DELETE"])
@login_required
def delete_invoice(invoice_id):
    state["invoices"] = [inv for inv in state["invoices"] if inv["id"] != invoice_id]
    return jsonify({"status": "deleted"})

@app.route("/api/invoices/upload", methods=["POST"])
@login_required
def upload_invoice():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier"}), 400
    file = request.files["file"]
    if not file.filename.endswith(".pdf"):
        return jsonify({"error": "PDF uniquement"}), 400

    inv_id = str(uuid.uuid4())[:8]
    filename = f"manual_{inv_id}_{file.filename}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(path)

    invoice = {
        "id": inv_id,
        "name": file.filename,
        "date": "—",
        "amount": "—",
        "source": "Manuel",
        "path": path,
        "selected": True,
    }
    state["invoices"].append(invoice)
    return jsonify(invoice)

@app.route("/uploads/<path:filename>")
@login_required
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ── Connecteurs dynamiques ─────────────────────────────────

@app.route("/api/connectors", methods=["GET"])
@login_required
def get_connectors():
    connectors = load_connectors()
    # On masque les mots de passe dans la réponse
    safe = []
    for c in connectors:
        safe.append({**c, "password": "••••••••"})
    return jsonify(safe)

@app.route("/api/connectors", methods=["POST"])
@login_required
def add_connector():
    data = request.get_json()
    required = ["name", "login_url", "invoices_url", "css_selector", "login", "password"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Champ manquant : {field}"}), 400

    connectors = load_connectors()

    # Vérifier qu'il n'existe pas déjà un connecteur avec ce nom
    slug = data["name"].lower().replace(" ", "_")
    if any(c["slug"] == slug for c in connectors):
        return jsonify({"error": f"Un connecteur '{data['name']}' existe déjà"}), 400

    connector = {
        "id": str(uuid.uuid4())[:8],
        "slug": slug,
        "name": data["name"],
        "login_url": data["login_url"],
        "invoices_url": data["invoices_url"],
        "css_selector": data["css_selector"],
        "login": data["login"],
        "password": data["password"],
        "enabled": True,
    }
    connectors.append(connector)
    save_connectors(connectors)
    return jsonify({**connector, "password": "••••••••"})

@app.route("/api/connectors/<connector_id>", methods=["DELETE"])
@login_required
def delete_connector(connector_id):
    connectors = load_connectors()
    connectors = [c for c in connectors if c["id"] != connector_id]
    save_connectors(connectors)
    return jsonify({"status": "deleted"})

@app.route("/api/connectors/<connector_id>/toggle", methods=["POST"])
@login_required
def toggle_connector(connector_id):
    connectors = load_connectors()
    for c in connectors:
        if c["id"] == connector_id:
            c["enabled"] = not c.get("enabled", True)
            save_connectors(connectors)
            return jsonify({**c, "password": "••••••••"})
    return jsonify({"error": "Connecteur introuvable"}), 404

if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)