import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Portage salarial", page_icon="💼", layout="wide")

sys.path.insert(0, ".")
from utils.auth import require_auth
require_auth()

# =========================
# Protection spécifique page
# =========================

PAGE_PASSWORD = st.secrets.get("portage_password", "demo_portage")

if "portage_auth" not in st.session_state:
    st.session_state.portage_auth = False


def protect_portage_page() -> None:
    st.title("🔒 Accès Portage salarial")
    st.write("Cette page est protégée par un mot de passe spécifique.")

    password = st.text_input(
        "Mot de passe Portage salarial",
        type="password",
        key="portage_page_password",
    )

    if st.button("Entrer sur la page", key="portage_page_button"):
        if password == PAGE_PASSWORD:
            st.session_state.portage_auth = True
            st.success("Accès autorisé")
            st.rerun()
        else:
            st.error("Mot de passe incorrect")


if not st.session_state.get("authenticated", False):
    st.warning("Merci de vous connecter d'abord à l'application principale.")
    st.stop()

if not st.session_state.portage_auth:
    protect_portage_page()
    st.stop()

# =========================
# Configuration
# =========================

MAX_JOURS_ANNUELS = 218
SAVE_FILE = Path("portage_salarial_data.json")

# Ratios calibrés à partir de la fiche de paie fournie
DEFAULT_MANAGEMENT_FEE_RATE = 0.04
DEFAULT_EMPLOYER_CHARGES_RATE = 2159.57 / 4498.41
DEFAULT_EMPLOYEE_CHARGES_RATE = 945.11 / 4498.41
DEFAULT_NET_TAXABLE_RATE = 3683.43 / 4498.41
DEFAULT_PAS_RATE = 346.24 / 3683.43
DEFAULT_TJM = 500.0

FISCAL_MONTHS = [
    ("Octobre", 10),
    ("Novembre", 11),
    ("Décembre", 12),
    ("Janvier", 1),
    ("Février", 2),
    ("Mars", 3),
    ("Avril", 4),
    ("Mai", 5),
    ("Juin", 6),
    ("Juillet", 7),
    ("Août", 8),
    ("Septembre", 9),
]

# =========================
# Helpers
# =========================


def format_currency(x: float) -> str:
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")


def guessed_fiscal_start_year() -> int:
    today = date.today()
    return today.year if today.month >= 10 else today.year - 1


def build_fiscal_year_df(start_year: int, default_tjm: float = DEFAULT_TJM) -> pd.DataFrame:
    rows = []
    for month_name, month_num in FISCAL_MONTHS:
        year = start_year if month_num >= 10 else start_year + 1
        rows.append(
            {
                "Année": year,
                "Mois": month_name,
                "Mois_num": month_num,
                "Jours travaillés": 0.0,
                "TJM": default_tjm,
                "Frais remboursés": 0.0,
            }
        )
    return pd.DataFrame(rows)


def default_settings() -> dict:
    return {
        "fiscal_start_year": guessed_fiscal_start_year(),
        "management_fee_rate": DEFAULT_MANAGEMENT_FEE_RATE,
        "employer_charges_rate": DEFAULT_EMPLOYER_CHARGES_RATE,
        "employee_charges_rate": DEFAULT_EMPLOYEE_CHARGES_RATE,
        "net_taxable_rate": DEFAULT_NET_TAXABLE_RATE,
        "pas_rate": DEFAULT_PAS_RATE,
        "default_tjm": DEFAULT_TJM,
    }


def save_data(settings: dict, cra_df: pd.DataFrame) -> None:
    payload = {
        "settings": settings,
        "cra": cra_df.to_dict(orient="records"),
    }
    SAVE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_data() -> tuple[dict, pd.DataFrame]:
    settings = default_settings()
    df = build_fiscal_year_df(
        settings["fiscal_start_year"],
        settings["default_tjm"],
    )

    if SAVE_FILE.exists():
        try:
            payload = json.loads(SAVE_FILE.read_text(encoding="utf-8"))
            settings.update(payload.get("settings", {}))
            cra_records = payload.get("cra", [])
            if cra_records:
                df = pd.DataFrame(cra_records)
        except Exception:
            pass

    return settings, df


def reset_fiscal_year(start_year: int, default_tjm: float) -> pd.DataFrame:
    return build_fiscal_year_df(start_year, default_tjm)


def simulate_row(
    days_worked: float,
    tjm: float,
    reimbursed_expenses: float,
    management_fee_rate: float,
    employer_charges_rate: float,
    employee_charges_rate: float,
    net_taxable_rate: float,
    pas_rate: float,
) -> dict:
    ca = days_worked * tjm
    management_fees = ca * management_fee_rate
    ca_after_management = ca - management_fees

    # Les frais remboursés sont retirés du disponible pour le salaire
    available_for_salary_cost = max(ca_after_management - reimbursed_expenses, 0.0)

    gross_salary = (
        available_for_salary_cost / (1 + employer_charges_rate)
        if available_for_salary_cost > 0
        else 0.0
    )

    employer_charges = gross_salary * employer_charges_rate
    employee_charges = gross_salary * employee_charges_rate
    net_social = gross_salary - employee_charges
    net_taxable = gross_salary * net_taxable_rate
    pas = net_taxable * pas_rate

    # Sur la logique de la fiche fournie, le net avant impôt inclut les frais remboursés
    net_before_income_tax = net_social + reimbursed_expenses
    net_after_income_tax = net_before_income_tax - pas

    return {
        "CA": ca,
        "Frais de gestion": management_fees,
        "CA après gestion": ca_after_management,
        "Coût disponible pour salaire": available_for_salary_cost,
        "Salaire brut": gross_salary,
        "Charges patronales": employer_charges,
        "Cotisations salariales": employee_charges,
        "Net social": net_social,
        "Net imposable": net_taxable,
        "PAS estimé": pas,
        "Net avant impôt": net_before_income_tax,
        "Net après impôt": net_after_income_tax,
    }


def simulate_dataframe(cra_df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    results = []
    for _, row in cra_df.iterrows():
        results.append(
            {
                "Année": row["Année"],
                "Mois": row["Mois"],
                "Jours travaillés": float(row["Jours travaillés"]),
                "TJM": float(row["TJM"]),
                "Frais remboursés": float(row["Frais remboursés"]),
                **simulate_row(
                    days_worked=float(row["Jours travaillés"]),
                    tjm=float(row["TJM"]),
                    reimbursed_expenses=float(row["Frais remboursés"]),
                    management_fee_rate=float(settings["management_fee_rate"]),
                    employer_charges_rate=float(settings["employer_charges_rate"]),
                    employee_charges_rate=float(settings["employee_charges_rate"]),
                    net_taxable_rate=float(settings["net_taxable_rate"]),
                    pas_rate=float(settings["pas_rate"]),
                ),
            }
        )
    return pd.DataFrame(results)


# =========================
# Initialisation
# =========================

if "portage_settings" not in st.session_state or "cra_df" not in st.session_state:
    settings, cra_df = load_data()
    st.session_state.portage_settings = settings
    st.session_state.cra_df = cra_df

settings = st.session_state.portage_settings
cra_df = st.session_state.cra_df

st.title("💼 Portage salarial")
st.caption(
    "Suivi CRA sur année fiscale octobre → septembre et simulation de paie calibrée sur la fiche fournie."
)

tab_cra, tab_simulation, tab_parametres = st.tabs(
    ["Suivi CRA", "Simulation salaire", "Paramètres"]
)

# =========================
# Onglet 1 : Suivi CRA
# =========================

with tab_cra:
    st.subheader("Compte rendu d'activité")

    left, right = st.columns([3, 1])

    with left:
        st.markdown(
            f"**Année fiscale :** octobre {settings['fiscal_start_year']} → septembre {settings['fiscal_start_year'] + 1}"
        )

    with right:
        if st.button("Sauvegarder", key="save_cra"):
            save_data(settings, st.session_state.cra_df)
            st.success("Données sauvegardées")

    st.info("Modifie les valeurs puis clique sur le bouton de validation en dessous.")

    with st.form("cra_form"):
        edited_df = st.data_editor(
            st.session_state.cra_df,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key="cra_editor",
            column_config={
                "Année": st.column_config.NumberColumn(disabled=True),
                "Mois": st.column_config.TextColumn(disabled=True),
                "Mois_num": st.column_config.NumberColumn(disabled=True),
                "Jours travaillés": st.column_config.NumberColumn(
                    min_value=0.0,
                    max_value=31.0,
                    step=0.5,
                ),
                "TJM": st.column_config.NumberColumn(
                    min_value=0.0,
                    step=10.0,
                    format="%.2f",
                ),
                "Frais remboursés": st.column_config.NumberColumn(
                    min_value=0.0,
                    step=10.0,
                    format="%.2f",
                ),
            },
        )

        submitted = st.form_submit_button("✅ Valider les modifications")

        if submitted:
            st.session_state.cra_df = edited_df.copy()
            st.success("Modifications enregistrées")
            st.rerun()

    cra_df = st.session_state.cra_df

    total_days = float(cra_df["Jours travaillés"].sum())
    remaining_days = MAX_JOURS_ANNUELS - total_days
    average_tjm = float(cra_df["TJM"].mean()) if len(cra_df) else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Jours cumulés", f"{total_days:.1f}")
    c2.metric("Jours restants", f"{remaining_days:.1f}")
    c3.metric("Plafond annuel", f"{MAX_JOURS_ANNUELS}")
    c4.metric("TJM moyen", format_currency(average_tjm))

    if total_days > MAX_JOURS_ANNUELS:
        st.error(
            f"Le plafond annuel est dépassé de {total_days - MAX_JOURS_ANNUELS:.1f} jours."
        )
    else:
        st.success("Le cumul reste dans la limite de 218 jours.")

# =========================
# Onglet 2 : Simulation salaire
# =========================

with tab_simulation:
    st.subheader("Simulation mensuelle et annuelle")

    results_df = simulate_dataframe(cra_df, settings)

    monthly_view = results_df[
        [
            "Année",
            "Mois",
            "Jours travaillés",
            "TJM",
            "CA",
            "Frais de gestion",
            "CA après gestion",
            "Frais remboursés",
            "Salaire brut",
            "Net social",
            "Net avant impôt",
            "PAS estimé",
            "Net après impôt",
        ]
    ].copy()

    st.dataframe(
        monthly_view.style.format(
            {
                "Jours travaillés": "{:.1f}",
                "TJM": lambda x: format_currency(x),
                "CA": lambda x: format_currency(x),
                "Frais de gestion": lambda x: format_currency(x),
                "CA après gestion": lambda x: format_currency(x),
                "Frais remboursés": lambda x: format_currency(x),
                "Salaire brut": lambda x: format_currency(x),
                "Net social": lambda x: format_currency(x),
                "Net avant impôt": lambda x: format_currency(x),
                "PAS estimé": lambda x: format_currency(x),
                "Net après impôt": lambda x: format_currency(x),
            }
        ),
        use_container_width=True,
    )

    totals = {
        "CA total": results_df["CA"].sum(),
        "Frais de gestion": results_df["Frais de gestion"].sum(),
        "Frais remboursés": results_df["Frais remboursés"].sum(),
        "Brut total": results_df["Salaire brut"].sum(),
        "Net social total": results_df["Net social"].sum(),
        "Net avant impôt total": results_df["Net avant impôt"].sum(),
        "PAS total": results_df["PAS estimé"].sum(),
        "Net après impôt total": results_df["Net après impôt"].sum(),
    }

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("CA total", format_currency(totals["CA total"]))
    a2.metric("Brut total", format_currency(totals["Brut total"]))
    a3.metric("Net social total", format_currency(totals["Net social total"]))
    a4.metric("Net avant impôt total", format_currency(totals["Net avant impôt total"]))

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Frais de gestion", format_currency(totals["Frais de gestion"]))
    b2.metric("Frais remboursés", format_currency(totals["Frais remboursés"]))
    b3.metric("PAS total estimé", format_currency(totals["PAS total"]))
    b4.metric("Net après impôt", format_currency(totals["Net après impôt total"]))

    csv_data = results_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Télécharger la simulation CSV",
        data=csv_data,
        file_name=(
            f"simulation_portage_{settings['fiscal_start_year']}_"
            f"{settings['fiscal_start_year'] + 1}.csv"
        ),
        mime="text/csv",
    )

# =========================
# Onglet 3 : Paramètres
# =========================

with tab_parametres:
    st.subheader("Paramètres du modèle")

    left, right = st.columns(2)

    with left:
        new_start_year = st.number_input(
            "Année fiscale de départ",
            min_value=2020,
            max_value=2100,
            value=int(settings["fiscal_start_year"]),
            step=1,
        )

        new_default_tjm = st.number_input(
            "TJM par défaut (€)",
            min_value=0.0,
            value=float(settings["default_tjm"]),
            step=10.0,
        )

        new_management_fee = st.number_input(
            "Frais de gestion (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(settings["management_fee_rate"] * 100),
            step=0.1,
        ) / 100

        new_pas_rate = st.number_input(
            "Taux PAS (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(settings["pas_rate"] * 100),
            step=0.1,
        ) / 100

    with right:
        new_employer_charges = st.number_input(
            "Charges patronales (% du brut)",
            min_value=0.0,
            max_value=100.0,
            value=float(settings["employer_charges_rate"] * 100),
            step=0.1,
        ) / 100

        new_employee_charges = st.number_input(
            "Cotisations salariales (% du brut)",
            min_value=0.0,
            max_value=100.0,
            value=float(settings["employee_charges_rate"] * 100),
            step=0.1,
        ) / 100

        new_net_taxable_rate = st.number_input(
            "Net imposable / brut (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(settings["net_taxable_rate"] * 100),
            step=0.1,
        ) / 100

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("Mettre à jour les paramètres", key="update_params"):
            st.session_state.portage_settings = {
                "fiscal_start_year": int(new_start_year),
                "management_fee_rate": float(new_management_fee),
                "employer_charges_rate": float(new_employer_charges),
                "employee_charges_rate": float(new_employee_charges),
                "net_taxable_rate": float(new_net_taxable_rate),
                "pas_rate": float(new_pas_rate),
                "default_tjm": float(new_default_tjm),
            }
            st.success("Paramètres mis à jour")
            st.rerun()

    with c2:
        if st.button("Appliquer le TJM par défaut", key="apply_default_tjm"):
            st.session_state.cra_df["TJM"] = float(new_default_tjm)
            st.success("TJM appliqué à tous les mois")
            st.rerun()

    with c3:
        if st.button("Réinitialiser l'année fiscale", key="reset_fiscal_year"):
            st.session_state.portage_settings = {
                "fiscal_start_year": int(new_start_year),
                "management_fee_rate": float(new_management_fee),
                "employer_charges_rate": float(new_employer_charges),
                "employee_charges_rate": float(new_employee_charges),
                "net_taxable_rate": float(new_net_taxable_rate),
                "pas_rate": float(new_pas_rate),
                "default_tjm": float(new_default_tjm),
            }
            st.session_state.cra_df = reset_fiscal_year(
                int(new_start_year),
                float(new_default_tjm),
            )
            st.success("Nouvelle année fiscale initialisée")
            st.rerun()

    if st.button("Sauvegarder paramètres et données", key="save_all"):
        save_data(st.session_state.portage_settings, st.session_state.cra_df)
        st.success(f"Données sauvegardées dans {SAVE_FILE}")

    with st.expander("Hypothèses de calcul"):
        st.markdown(
            f"""
- **Frais de gestion** : {st.session_state.portage_settings['management_fee_rate'] * 100:.2f}% du CA
- **Charges patronales** : {st.session_state.portage_settings['employer_charges_rate'] * 100:.2f}% du brut
- **Cotisations salariales** : {st.session_state.portage_settings['employee_charges_rate'] * 100:.2f}% du brut
- **Net imposable / brut** : {st.session_state.portage_settings['net_taxable_rate'] * 100:.2f}%
- **PAS** : {st.session_state.portage_settings['pas_rate'] * 100:.2f}% du net imposable

Il sert à la prévision et au pilotage, pas à reproduire au centime tous les bulletins futurs.
"""
        )