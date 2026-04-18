import streamlit as st
import json
import os
import sys
sys.path.insert(0, ".")
from utils.auth import require_auth

require_auth()

st.title("🏠 Simulation projet immobilier (Couple avancé)")

# --- FICHIERS ---
CHARGES_FILE = "charges.json"
INPUT_FILE = "immo_inputs.json"

# --- Charger / sauvegarder inputs ---
def load_inputs():
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r") as f:
            return json.load(f)
    return {}

def save_inputs(data):
    with open(INPUT_FILE, "w") as f:
        json.dump(data, f)

inputs = load_inputs()

# --- Charger charges ---
if os.path.exists(CHARGES_FILE):
    with open(CHARGES_FILE, "r") as f:
        charges_data = json.load(f)
else:
    charges_data = []

# --- Sécurisation ---
def normalize_pay(value):
    return value if value in ["Mari", "Femme"] else "Mari"

# --- Calcul charges hors loyer ---
charges_mari = 0
charges_femme = 0

for c in charges_data:
    montant = c.get("montant", 0)
    payeur = normalize_pay(c.get("payeur"))
    nom = c.get("nom", "").lower()

    if "loyer" in nom:
        continue

    if payeur == "Mari":
        charges_mari += montant
    else:
        charges_femme += montant

charges_total = charges_mari + charges_femme

# --- Revenus ---
st.subheader("💰 Revenus")

revenu_mari = st.number_input("Revenu Mari (€)", value=inputs.get("revenu_mari", 3000))
revenu_femme = st.number_input("Revenu Femme (€)", value=inputs.get("revenu_femme", 2500))

revenu_total = revenu_mari + revenu_femme

# --- Paramètres ---
st.subheader("🏡 Paramètres")

taux = st.number_input("Taux (%)", value=inputs.get("taux", 3.5))
duree = st.number_input("Durée (années)", value=inputs.get("duree", 23))
apport_pct = st.number_input("Apport (%)", value=inputs.get("apport", 10))

mode = st.radio("Mode de calcul", ["Mensualité → Projet", "Projet → Mensualité"])

taux_mensuel = taux / 100 / 12
nb_mois = duree * 12

# --- MODE 1 ---
if mode == "Mensualité → Projet":

    mensualite = st.number_input(
        "Mensualité souhaitée (€)",
        value=inputs.get("mensualite", 2000)
    )

    if taux_mensuel > 0:
        capital = mensualite * (1 - (1 + taux_mensuel) ** -nb_mois) / taux_mensuel
    else:
        capital = mensualite * nb_mois

    # 🔥 AJOUT APPORT
    prix_bien = capital / (1 - apport_pct / 100)

# --- MODE 2 ---
else:

    prix_bien = st.number_input(
        "Prix du bien (€)",
        value=inputs.get("prix_bien", 400000)
    )

    capital = prix_bien * (1 - apport_pct / 100)

    if taux_mensuel > 0:
        mensualite = capital * taux_mensuel / (1 - (1 + taux_mensuel) ** -nb_mois)
    else:
        mensualite = capital / nb_mois

# --- Sauvegarde ---
save_inputs({
    "revenu_mari": revenu_mari,
    "revenu_femme": revenu_femme,
    "taux": taux,
    "duree": duree,
    "mensualite": mensualite,
    "capital": capital,
    "prix_bien": prix_bien,
    "apport": apport_pct
})

# --- Calculs ---
taux_endettement = (mensualite / revenu_total) * 100

mensualite_mari = mensualite * 0.75
mensualite_femme = mensualite * 0.25

reste_mari = revenu_mari - charges_mari - mensualite_mari
reste_femme = revenu_femme - charges_femme - mensualite_femme
reste_total = revenu_total - charges_total - mensualite

# --- Résultats ---
st.subheader("📊 Résultats")

st.write(f"🏠 Prix du bien : {prix_bien:.0f} €")
st.write(f"💰 Apport : {(prix_bien - capital):.0f} €")
st.write(f"🏦 Montant emprunté : {capital:.0f} €")
st.write(f"💳 Mensualité : {mensualite:.0f} €")

# --- Endettement ---
st.subheader("🏦 Endettement")

st.write(f"Taux : {taux_endettement:.1f} %")

if taux_endettement < 35:
    st.success("✅ OK banque")
else:
    st.error("⚠️ Trop élevé")

# --- Reste à vivre ---
st.subheader("💸 Reste à vivre")

st.write(f"👨 Mari : {reste_mari:.0f} €")
st.write(f"👩 Femme : {reste_femme:.0f} €")
st.write(f"👥 Total : {reste_total:.0f} €")

# --- Analyse ---
st.subheader("🧠 Analyse")

if reste_total > 1500:
    st.success("🟢 Confortable")
elif reste_total > 800:
    st.warning("🟠 À surveiller")
else:
    st.error("🔴 Risqué")