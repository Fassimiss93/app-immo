import streamlit as st
import json
import os

st.title("💸 Suivi des charges (Couple)")

FILE_PATH = "charges.json"

# --- Charger les données ---
if os.path.exists(FILE_PATH):
    with open(FILE_PATH, "r") as f:
        charges = json.load(f)
else:
    charges = []

# --- Fonction de nettoyage (important) ---
def normalize_affectation(value):
    if value in ["Perso", "Couple"]:
        return value
    else:
        return "Perso"  # fallback propre

def normalize_payeur(value):
    if value in ["Mari", "Femme"]:
        return value
    else:
        return "Mari"

# --- Ajouter une charge ---
st.subheader("➕ Ajouter une charge")

nom = st.text_input("Nom de la charge")
montant = st.number_input("Montant (€)", min_value=0.0, step=10.0)

affectation = st.selectbox("Type de charge", ["Perso", "Couple"])
payeur = st.selectbox("Qui paye ?", ["Mari", "Femme"])

if st.button("Ajouter la charge"):
    if nom and montant > 0:
        charges.append({
            "nom": nom,
            "montant": montant,
            "affectation": affectation,
            "payeur": payeur
        })

        with open(FILE_PATH, "w") as f:
            json.dump(charges, f)

        st.success("Charge ajoutée")
        st.rerun()
    else:
        st.warning("Merci de remplir les champs")

# --- FILTRE ---
st.subheader("🔍 Filtrer")

filtre = st.radio("Afficher :", ["Toutes", "Perso", "Couple"], horizontal=True)

if filtre == "Toutes":
    charges_filtrees = charges
else:
    charges_filtrees = [
        c for c in charges if normalize_affectation(c.get("affectation")) == filtre
    ]

# --- Affichage + modification ---
st.subheader("📋 Liste des charges")

for charge in charges_filtrees:

    index_reel = charges.index(charge)

    nom_c = charge.get("nom", "")
    montant_c = charge.get("montant", 0)

    aff_c = normalize_affectation(charge.get("affectation"))
    pay_c = normalize_payeur(charge.get("payeur"))

    col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])

    col1.write(nom_c)
    col2.write(f"{montant_c:.0f} €")

    new_aff = col3.selectbox(
        "Type",
        ["Perso", "Couple"],
        index=0 if aff_c == "Perso" else 1,
        key=f"aff_{index_reel}"
    )

    new_pay = col4.selectbox(
        "Payé par",
        ["Mari", "Femme"],
        index=0 if pay_c == "Mari" else 1,
        key=f"pay_{index_reel}"
    )

    # Sauvegarde si modif
    if new_aff != aff_c or new_pay != pay_c:
        charges[index_reel]["affectation"] = new_aff
        charges[index_reel]["payeur"] = new_pay

        with open(FILE_PATH, "w") as f:
            json.dump(charges, f)

        st.rerun()

    # Supprimer
    if col5.button("❌", key=f"del_{index_reel}"):
        charges.pop(index_reel)
        with open(FILE_PATH, "w") as f:
            json.dump(charges, f)
        st.rerun()

# --- Calculs ---
total_perso_mari = 0
total_perso_femme = 0
total_couple = 0

part_mari = 0
part_femme = 0

for charge in charges:
    montant = charge.get("montant", 0)
    aff = normalize_affectation(charge.get("affectation"))
    pay = normalize_payeur(charge.get("payeur"))

    if aff == "Perso":
        if pay == "Mari":
            total_perso_mari += montant
        else:
            total_perso_femme += montant
    else:
        total_couple += montant

    if pay == "Mari":
        part_mari += montant
    else:
        part_femme += montant

# --- Totaux ---
st.subheader("📊 Totaux")

st.write(f"👨 Perso Mari : {total_perso_mari:.0f} €")
st.write(f"👩 Perso Femme : {total_perso_femme:.0f} €")
st.write(f"👥 Charges couple : {total_couple:.0f} €")

# --- Répartition réelle ---
st.subheader("📈 Qui paye réellement")

total_global = part_mari + part_femme

if total_global > 0:
    pct_mari = (part_mari / total_global) * 100
    pct_femme = (part_femme / total_global) * 100

    st.write(f"👨 Mari : {part_mari:.0f} € ({pct_mari:.1f}%)")
    st.write(f"👩 Femme : {part_femme:.0f} € ({pct_femme:.1f}%)")
else:
    st.write("Aucune charge")