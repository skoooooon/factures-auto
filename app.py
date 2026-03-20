import os
import json
import threading
from flask import Flask, render_template, jsonify, request, send_from_directory
from collector import run_collection
from sender import send_to_pennylane

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"

# État partagé entre les threads
state = {
    "collecting": False,
    "sending": False,
    "logs": [],
    "invoices": [],  # [{"id": str, "name": str, "date": str, "amount": str, "source": str, "path": str, "selected": bool}]
}

def log(msg):
    state["logs"].append(msg)
    print(msg)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/collect", methods=["POST"])
def collect():
    if state["collecting"]:
        return jsonify({"error": "Collecte déjà en cours"}), 400
    state["collecting"] = True
    state["logs"] = []
    state["invoices"] = []

    def run():
        try:
            run_collection(state, log)
        finally:
            state["collecting"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/api/send", methods=["POST"])
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
def status():
    return jsonify({
        "collecting": state["collecting"],
        "sending": state["sending"],
        "logs": state["logs"][-50:],  # 50 derniers logs
        "invoices": state["invoices"],
    })

@app.route("/api/invoices/<invoice_id>/toggle", methods=["POST"])
def toggle_invoice(invoice_id):
    for inv in state["invoices"]:
        if inv["id"] == invoice_id:
            inv["selected"] = not inv.get("selected", True)
            return jsonify(inv)
    return jsonify({"error": "Facture introuvable"}), 404

@app.route("/api/invoices/<invoice_id>", methods=["DELETE"])
def delete_invoice(invoice_id):
    state["invoices"] = [inv for inv in state["invoices"] if inv["id"] != invoice_id]
    return jsonify({"status": "deleted"})

@app.route("/api/invoices/upload", methods=["POST"])
def upload_invoice():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier"}), 400
    file = request.files["file"]
    if not file.filename.endswith(".pdf"):
        return jsonify({"error": "PDF uniquement"}), 400

    import uuid
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
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
