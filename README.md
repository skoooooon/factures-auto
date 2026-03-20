# Factures Auto

Collecte automatique des factures PDF depuis Gmail et les espaces clients,
avec envoi vers Pennylane en un clic.

---

## Structure du projet

```
factures-auto/
├── app.py               ← Serveur Flask (routes API + interface)
├── collector.py         ← Orchestrateur de collecte
├── sender.py            ← Envoi vers Pennylane par email
├── connectors/
│   ├── gmail.py         ← Collecte via API Gmail
│   ├── total.py         ← Scraping Total Energies
│   ├── aprr.py          ← Scraping APRR
│   ├── easyjet.py       ← Scraping EasyJet
│   └── _template.py     ← Template pour ajouter un service
├── templates/
│   └── index.html       ← Interface web
├── requirements.txt
└── railway.toml
```

---

## Déploiement sur Railway

### 1. Préparer le repo GitHub
```bash
cd factures-auto
git init
git add .
git commit -m "Initial commit"
# Créer un repo sur GitHub, puis :
git remote add origin https://github.com/VOTRE_USERNAME/factures-auto.git
git push -u origin main
```

### 2. Créer le projet sur Railway
1. Aller sur https://railway.app
2. "New Project" → "Deploy from GitHub repo"
3. Sélectionner votre repo `factures-auto`
4. Railway détecte automatiquement le projet Python

### 3. Configurer les variables d'environnement sur Railway
Dans Railway > votre projet > "Variables", ajouter :

| Variable           | Valeur                                      |
|--------------------|---------------------------------------------|
| `PENNYLANE_EMAIL`  | L'adresse de dépôt Pennylane (dans les paramètres Pennylane) |
| `SMTP_EMAIL`       | Votre adresse Gmail                         |
| `SMTP_PASSWORD`    | Mot de passe d'application Gmail (voir ci-dessous) |
| `TOTAL_LOGIN`      | Email compte Total                          |
| `TOTAL_PASSWORD`   | Mot de passe Total                          |
| `APRR_LOGIN`       | Email compte APRR                           |
| `APRR_PASSWORD`    | Mot de passe APRR                           |
| `EASYJET_LOGIN`    | Email compte EasyJet                        |
| `EASYJET_PASSWORD` | Mot de passe EasyJet                        |

### 4. Créer un mot de passe d'application Gmail (SMTP_PASSWORD)
⚠️ Ne jamais utiliser votre mot de passe Google principal.

1. Aller sur https://myaccount.google.com/security
2. Activer la validation en 2 étapes si ce n'est pas fait
3. Chercher "Mots de passe des applications"
4. Créer un mot de passe pour "Autre application" → nommer "Factures Auto"
5. Copier le mot de passe généré (16 caractères) → c'est votre `SMTP_PASSWORD`

### 5. Configurer l'API Gmail (pour la collecte Gmail)
1. Aller sur https://console.cloud.google.com
2. Créer un nouveau projet "Factures Auto"
3. Activer l'API Gmail : "APIs & Services" → "Bibliothèque" → chercher "Gmail API"
4. Créer des identifiants OAuth 2.0 :
   - "APIs & Services" → "Identifiants" → "Créer des identifiants" → "ID client OAuth"
   - Type : "Application de bureau"
   - Télécharger le fichier JSON → renommer en `credentials.json`
   - Placer `credentials.json` à la racine du projet
5. Au premier lancement, une fenêtre s'ouvre pour autoriser → `token.json` est créé
   (Pour Railway : générer `token.json` en local d'abord, puis l'ajouter au repo)

---

## Ajouter un nouveau connecteur

1. Copier `connectors/_template.py` → `connectors/monservice.py`
2. Adapter l'URL de connexion et les sélecteurs CSS
3. Ajouter les variables d'environnement sur Railway (`MONSERVICE_LOGIN`, etc.)
4. Dans `collector.py`, décommenter/ajouter :
   ```python
   from connectors.monservice import collect_monservice
   # ...
   ("MonService", collect_monservice, "monservice"),
   ```

---

## Développement local

```bash
pip install -r requirements.txt
playwright install chromium

# Copier le fichier d'exemple
cp .env.example .env
# Remplir les valeurs dans .env

# Lancer en local
python app.py
# Ouvrir http://localhost:5000
```

---

## Notes importantes

- **Les connecteurs de scraping sont des points de départ** : les sélecteurs CSS
  dépendent de la structure exacte des sites, qui peut changer. Si un connecteur
  échoue, vérifiez d'abord les sélecteurs avec les outils développeur du navigateur.

- **EasyJet** envoie généralement les confirmations par email → Gmail les récupère
  automatiquement, le scraping est un filet de sécurité.

- **Stockage temporaire** : les PDFs sont stockés dans `/uploads` pendant la session.
  Ils sont effacés au redémarrage du serveur. Pennylane conserve les originaux.
