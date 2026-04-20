"""
Combiné Gagnant — Analyse multi-sports des cotes Unibet.

Stratégie :
  1. Récupère TOUS les matchs à venir avec cotes Unibet (The Odds API)
  2. Pour chaque issue, calcule la probabilité "juste" (consensus tous bookmakers, marge retirée)
  3. Score chaque sélection = EV = proba_modèle × cote_Unibet
  4. Prend le TOP N sélections pour construire des combinés
  5. Classe les combinés par score = proba_combinée × EV_moyen
"""

import streamlit as st
import requests
import pandas as pd
from datetime import date, datetime, timedelta
from itertools import combinations as _combinations
from typing import Dict, List, Optional, Tuple
import sys
sys.path.insert(0, ".")
from utils.auth import require_auth

st.set_page_config(page_title="🎯 Combiné Gagnant", layout="wide")
require_auth()

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ══════════════════════════════════════════════════════════════════════════════
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
AF_BASE       = "https://v3.football.api-sports.io"

UNIBET_KEYS = {"unibet_eu", "unibet", "unibet_fr", "unibet_de", "unibet_it", "unibet_es"}

SPORT_GROUPS = {
    "⚽ Football": [
        "soccer_epl", "soccer_spain_la_liga", "soccer_germany_bundesliga",
        "soccer_italy_serie_a", "soccer_france_ligue_one",
        "soccer_uefa_champs_league", "soccer_uefa_europa_league",
        "soccer_belgium_first_div", "soccer_netherlands_eredivisie",
        "soccer_portugal_primeira_liga", "soccer_turkey_super_league",
    ],
    "🏀 Basketball": [
        "basketball_nba", "basketball_euroleague",
        "basketball_nbl", "basketball_ncaab",
    ],
    "🎾 Tennis": [],           # rempli dynamiquement
    "🏒 Hockey": [
        "icehockey_nhl", "icehockey_sweden_hockey_league",
    ],
    "🏉 Rugby": [
        "rugbyleague_nrl", "rugbyunion_premiership", "rugbyunion_super_rugby",
    ],
    "⚾ Baseball": ["baseball_mlb"],
    "🥊 MMA": ["mma_mixed_martial_arts"],
    "🏈 Foot américain": ["americanfootball_nfl", "americanfootball_ncaaf"],
    "🏏 Cricket": ["cricket_ipl", "cricket_test_match"],
}

MARKET_LABELS = {
    "h2h":         "Résultat / Vainqueur",
    "totals":      "Over / Under buts/points",
    "btts":        "Les deux équipes marquent",
    "draw_no_bet": "Double chance sans nul",
    "spreads":     "Handicap asiatique",
}

AF_LEAGUE_IDS = {
    "soccer_epl": 39, "soccer_spain_la_liga": 140,
    "soccer_germany_bundesliga": 78, "soccer_italy_serie_a": 135,
    "soccer_france_ligue_one": 61, "soccer_uefa_champs_league": 2,
    "soccer_uefa_europa_league": 3,
}


# ══════════════════════════════════════════════════════════════════════════════
# RÉSEAU
# ══════════════════════════════════════════════════════════════════════════════

def _get(url: str, params: dict = None, headers: dict = None) -> Optional[object]:
    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_active_sports(api_key: str) -> List[Dict]:
    data = _get(f"{ODDS_API_BASE}/sports", params={"apiKey": api_key, "all": "false"})
    return data if isinstance(data, list) else []


@st.cache_data(ttl=900, show_spinner=False)
def fetch_odds(sport_key: str, api_key: str, markets: str) -> List[Dict]:
    data = _get(
        f"{ODDS_API_BASE}/sports/{sport_key}/odds",
        params={
            "apiKey": api_key, "regions": "eu",
            "markets": markets, "oddsFormat": "decimal", "dateFormat": "iso",
        },
    )
    return data if isinstance(data, list) else []


# ══════════════════════════════════════════════════════════════════════════════
# PROBABILITÉS
# ══════════════════════════════════════════════════════════════════════════════

def _remove_margin(outcomes: List[Dict]) -> Dict[str, float]:
    total = sum(1.0 / o["price"] for o in outcomes if o.get("price", 0) > 1.01)
    if not total:
        return {}
    return {o["name"]: (1.0 / o["price"]) / total for o in outcomes if o.get("price", 0) > 1.01}


def _consensus(game: Dict, mkey: str) -> Dict[str, float]:
    """Moyenne des probas justes de tous les bookmakers."""
    acc: Dict[str, List[float]] = {}
    for bm in game.get("bookmakers", []):
        for m in bm.get("markets", []):
            if m["key"] == mkey:
                for name, p in _remove_margin(m["outcomes"]).items():
                    acc.setdefault(name, []).append(p)
    return {k: sum(v) / len(v) for k, v in acc.items() if v}


def _unibet(game: Dict, mkey: str) -> Dict[str, float]:
    for bm in game.get("bookmakers", []):
        if bm["key"] in UNIBET_KEYS:
            for m in bm.get("markets", []):
                if m["key"] == mkey:
                    return {o["name"]: o["price"] for o in m["outcomes"]}
    return {}


def _best(game: Dict, mkey: str) -> Dict[str, float]:
    best: Dict[str, float] = {}
    for bm in game.get("bookmakers", []):
        for m in bm.get("markets", []):
            if m["key"] == mkey:
                for o in m["outcomes"]:
                    if o["price"] > best.get(o["name"], 0):
                        best[o["name"]] = o["price"]
    return best


def _n_books(game: Dict, mkey: str) -> int:
    return sum(1 for bm in game.get("bookmakers", [])
               for m in bm.get("markets", []) if m["key"] == mkey)


# ══════════════════════════════════════════════════════════════════════════════
# API-FOOTBALL
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_af_preds(date_iso: str, af_key: str) -> Dict[str, Dict]:
    if not af_key:
        return {}
    hdrs = {"x-rapidapi-key": af_key, "x-rapidapi-host": "v3.football.api-sports.io"}
    d = date.fromisoformat(date_iso)
    season = d.year if d.month >= 7 else d.year - 1
    result: Dict[str, Dict] = {}
    for lid in AF_LEAGUE_IDS.values():
        fixes = _get(f"{AF_BASE}/fixtures", params={"league": lid, "date": date_iso, "season": season}, headers=hdrs)
        if not fixes:
            continue
        for fix in fixes.get("response", []):
            fid  = fix.get("fixture", {}).get("id")
            home = fix.get("teams", {}).get("home", {}).get("name", "")
            away = fix.get("teams", {}).get("away", {}).get("name", "")
            if not (fid and home and away):
                continue
            pred = _get(f"{AF_BASE}/predictions", params={"fixture": fid}, headers=hdrs)
            if not pred or not pred.get("response"):
                continue
            pct = pred["response"][0].get("predictions", {}).get("percent", {})
            def _p(s):
                try: return float(str(s).replace("%", "")) / 100.0
                except: return None
            result[f"{home}|{away}"] = {
                "home_pct": _p(pct.get("home")),
                "draw_pct": _p(pct.get("draw")),
                "away_pct": _p(pct.get("away")),
            }
    return result


# ══════════════════════════════════════════════════════════════════════════════
# KELLY
# ══════════════════════════════════════════════════════════════════════════════

def kelly(prob: float, odds: float, frac: float = 0.25) -> float:
    if odds <= 1.01 or prob <= 0 or prob >= 1:
        return 0.0
    b = odds - 1.0
    return max(0.0, (prob * b - (1 - prob)) / b * frac)


# ══════════════════════════════════════════════════════════════════════════════
# SÉLECTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _markets_for(sport_key: str) -> str:
    if sport_key.startswith("soccer"):
        return "h2h,totals,btts,draw_no_bet"
    if sport_key.startswith(("basketball", "icehockey", "baseball", "americanfootball")):
        return "h2h,totals,spreads"
    return "h2h"


def build_selections(
    games: List[Dict],
    target_dates: List[date],
    af_preds: Dict[str, Dict],
    min_uni_odds: float,
    min_model_prob: float,
) -> List[Dict]:
    sels: List[Dict] = []

    for game in games:
        try:
            gdt = datetime.fromisoformat(game["commence_time"].replace("Z", "+00:00"))
            gdate = gdt.date()
            # On accepte aussi J-1 UTC (décalage horaire)
            if gdate not in target_dates and (gdate - timedelta(days=1)) not in target_dates:
                continue
            kickoff = gdt.strftime("%d/%m %H:%M")
        except Exception:
            continue

        home      = game.get("home_team", "?")
        away      = game.get("away_team", "?")
        sport_key = game.get("_sport_key", "")
        league    = game.get("_league", sport_key)
        match_id  = game.get("id", f"{home}|{away}")
        is_soccer = sport_key.startswith("soccer")

        af = af_preds.get(f"{home}|{away}", {})

        # Marchés présents dans ce match
        market_keys: set = set()
        for bm in game.get("bookmakers", []):
            for m in bm.get("markets", []):
                market_keys.add(m["key"])

        for mkey in market_keys:
            consensus = _consensus(game, mkey)
            uni_odds  = _unibet(game, mkey)
            best_odds = _best(game, mkey)
            nb        = _n_books(game, mkey)

            if not consensus or not uni_odds:
                continue

            for outcome, cons_prob in consensus.items():
                uni_odd = uni_odds.get(outcome)
                if not uni_odd or uni_odd < min_uni_odds:
                    continue

                # Affiner avec AF pour football h2h
                model_prob = cons_prob
                if is_soccer and mkey == "h2h" and af:
                    if outcome == home and af.get("home_pct"):
                        model_prob = 0.55 * cons_prob + 0.45 * af["home_pct"]
                    elif outcome == away and af.get("away_pct"):
                        model_prob = 0.55 * cons_prob + 0.45 * af["away_pct"]
                    elif "Draw" in outcome and af.get("draw_pct"):
                        model_prob = 0.55 * cons_prob + 0.45 * af["draw_pct"]

                if model_prob * 100 < min_model_prob:
                    continue

                ev       = model_prob * uni_odd          # EV > 1.0 = valeur positive
                edge_pct = (ev - 1.0) * 100             # % au-dessus de 1
                kly      = kelly(model_prob, uni_odd)
                best     = best_odds.get(outcome, uni_odd)

                sels.append({
                    "match_id":    match_id,
                    "sport_key":   sport_key,
                    "league":      league,
                    "match":       f"{home} — {away}",
                    "kickoff":     kickoff,
                    "kickoff_date":gdate,
                    "market_key":  mkey,
                    "market":      MARKET_LABELS.get(mkey, mkey),
                    "outcome":     outcome,
                    "model_prob":  round(model_prob * 100, 1),
                    "cons_prob":   round(cons_prob * 100, 1),
                    "unibet_odds": round(uni_odd, 2),
                    "best_odds":   round(best, 2),
                    "ev":          round(ev, 4),
                    "edge_pct":    round(edge_pct, 1),
                    "kelly_pct":   round(kly * 100, 1),
                    "n_books":     nb,
                    # Score global = combine proba ET valeur
                    "score":       round(model_prob * ev, 4),
                })

    sels.sort(key=lambda x: x["score"], reverse=True)
    return sels


# ══════════════════════════════════════════════════════════════════════════════
# COMBINÉS
# ══════════════════════════════════════════════════════════════════════════════

def build_combos(
    top_sels: List[Dict],
    min_combined_prob: float,
    max_fold: int,
    max_results: int,
) -> List[Dict]:
    results: List[Dict] = []

    for fold in range(2, max_fold + 1):
        for combo in _combinations(top_sels, fold):
            # Pas deux sélections du même match (sauf marchés différents ET sport différent → trop corrélé)
            match_ids = [s["match_id"] for s in combo]
            if len(set(match_ids)) < fold:
                continue

            comb_prob  = 1.0
            comb_uni   = 1.0
            comb_best  = 1.0
            total_edge = 0.0
            total_ev   = 0.0

            for s in combo:
                comb_prob  *= s["model_prob"] / 100.0
                comb_uni   *= s["unibet_odds"]
                comb_best  *= s["best_odds"]
                total_edge += s["edge_pct"]
                total_ev   += s["ev"]

            if comb_prob * 100 < min_combined_prob:
                continue

            avg_edge = total_edge / fold
            avg_ev   = total_ev / fold
            score    = comb_prob * avg_ev
            kly      = kelly(comb_prob, comb_uni)

            results.append({
                "fold":         fold,
                "selections":   list(combo),
                "comb_prob":    round(comb_prob * 100, 1),
                "unibet_odds":  round(comb_uni, 2),
                "best_odds":    round(comb_best, 2),
                "avg_edge":     round(avg_edge, 1),
                "avg_ev":       round(avg_ev, 4),
                "score":        score,
                "kelly_pct":    round(kly * 100, 1),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


# ══════════════════════════════════════════════════════════════════════════════
# INTERFACE
# ══════════════════════════════════════════════════════════════════════════════

st.title("🎯 Combiné Gagnant")
st.caption(
    "Multi-sports · Tous marchés Unibet · Probabilités consensus (marge retirée) · "
    "Combinés optimisés par valeur espérée."
)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Paramètres")

    st.subheader("🔑 Clés API")
    odds_key = st.text_input("The Odds API *", type="password",
                              value=st.secrets.get("odds_api_key", ""))
    af_key   = st.text_input("API-Football (optionnel)", type="password",
                              value=st.secrets.get("api_football_key", ""),
                              help="Améliore les probas football uniquement")

    st.divider()

    st.subheader("📅 Période")
    today = date.today()
    date_opt = st.radio("", ["Aujourd'hui", "Demain", "J+2", "Cette semaine (7j)"])
    if date_opt == "Aujourd'hui":
        target_dates = [today];           period_lbl = today.strftime("%d/%m/%Y")
    elif date_opt == "Demain":
        target_dates = [today+timedelta(1)]; period_lbl = target_dates[0].strftime("%d/%m/%Y")
    elif date_opt == "J+2":
        target_dates = [today+timedelta(2)]; period_lbl = target_dates[0].strftime("%d/%m/%Y")
    else:
        target_dates = [today+timedelta(i) for i in range(7)]
        period_lbl   = f"{today.strftime('%d/%m')} → {(today+timedelta(6)).strftime('%d/%m/%Y')}"
    st.info(f"📅 {period_lbl}")

    st.divider()

    st.subheader("🏟️ Sports")
    selected_groups = st.multiselect(
        "Catégories", list(SPORT_GROUPS.keys()),
        default=["⚽ Football", "🏀 Basketball", "🎾 Tennis", "🏒 Hockey"],
    )

    st.divider()

    st.subheader("🎯 Filtres sélections")
    min_model_prob = st.slider("Proba modèle min (%)", 40, 80, 50)
    min_uni_odds   = st.slider("Cote Unibet min", 1.05, 3.0, 1.10, step=0.05)
    top_n_sels     = st.slider(
        "Top N sélections pour les combinés", 10, 50, 30,
        help="On prend les N meilleures sélections (par score EV) pour construire les combinés.",
    )

    st.divider()

    st.subheader("🎰 Combinés")
    max_fold          = st.slider("Folds max", 2, 6, 4)
    if max_fold > 4:
        st.warning(f"⚠️ {max_fold}-fold : risque élevé.")
    min_combined_prob = st.slider("Proba combinée min (%)", 5, 65, 20)
    max_combos        = st.slider("Combinés à afficher", 5, 50, 25)
    only_positive_ev  = st.toggle("Sélections EV positif uniquement", value=False,
                                   help="Si activé, exclut les sélections où EV < 1.0 (edge négatif).")

    st.divider()
    if st.button("🗑️ Vider le cache", use_container_width=True):
        st.cache_data.clear()
        st.success("Cache vidé !")

# ── GARDE ─────────────────────────────────────────────────────────────────────
if not odds_key:
    st.error("🔑 Clé The Odds API requise.")
    st.stop()
if not selected_groups:
    st.warning("Sélectionne au moins un sport.")
    st.stop()

run = st.button(f"🚀 Générer les combinés — {period_lbl}", type="primary", use_container_width=True)
if not run:
    st.stop()

# ── FETCH ─────────────────────────────────────────────────────────────────────
with st.status("🔍 Récupération des cotes Unibet…", expanded=True) as status:

    active_sports = fetch_active_sports(odds_key)
    active_keys   = {s["key"] for s in active_sports}

    sports_to_fetch: List[Tuple[str, str]] = []
    for grp in selected_groups:
        if grp == "🎾 Tennis":
            for s in active_sports:
                if s["key"].startswith("tennis") and s.get("active"):
                    sports_to_fetch.append((s["key"], s.get("title", s["key"])))
        else:
            for sk in SPORT_GROUPS.get(grp, []):
                if sk in active_keys:
                    lbl = next((s.get("title", sk) for s in active_sports if s["key"] == sk), sk)
                    sports_to_fetch.append((sk, lbl))

    st.write(f"✅ {len(sports_to_fetch)} compétition(s) active(s).")

    all_games: List[Dict] = []
    for sport_key, league_lbl in sports_to_fetch:
        markets_str = _markets_for(sport_key)
        games = fetch_odds(sport_key, odds_key, markets_str)
        for g in games:
            g["_sport_key"] = sport_key
            g["_league"]    = league_lbl
        all_games.extend(games)
        if games:
            st.write(f"  ✓ {league_lbl} — {len(games)} match(s)")

    st.write(f"**Total : {len(all_games)} matchs récupérés.**")

    af_preds: Dict[str, Dict] = {}
    if af_key:
        st.write("🤖 Prédictions API-Football…")
        for d in target_dates:
            af_preds.update(fetch_af_preds(d.isoformat(), af_key))
        st.write(f"  → {len(af_preds)} prédiction(s).")

    status.update(label=f"✅ {len(all_games)} matchs analysés.", state="complete")

if not all_games:
    st.error("Aucun match trouvé. Vérifie la clé ou change de période.")
    st.stop()

# ── SÉLECTIONS ────────────────────────────────────────────────────────────────
all_sels = build_selections(all_games, target_dates, af_preds, min_uni_odds, min_model_prob)

if only_positive_ev:
    pool = [s for s in all_sels if s["ev"] >= 1.0]
else:
    pool = all_sels

top_sels = pool[:top_n_sels]

# ── KPIs ──────────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Matchs avec cotes", len({s["match_id"] for s in all_sels}))
k2.metric("Sélections trouvées", len(all_sels))
k3.metric(f"Top {top_n_sels} pour combinés", len(top_sels))

combos = build_combos(top_sels, min_combined_prob, max_fold, max_combos)
k4.metric("Combinés générés", len(combos))

st.divider()

# ── SÉLECTIONS (tableau) ──────────────────────────────────────────────────────
with st.expander(f"📋 Top {top_n_sels} sélections utilisées pour les combinés", expanded=False):
    if top_sels:
        df_sels = pd.DataFrame(top_sels)[[
            "kickoff", "league", "match", "market", "outcome",
            "model_prob", "cons_prob", "edge_pct", "unibet_odds", "best_odds", "n_books",
        ]]
        df_sels.columns = [
            "Heure", "Compétition", "Match", "Marché", "Issue",
            "Proba modèle %", "Proba consensus %", "Edge %",
            "Cote Unibet", "Meilleure cote", "# Books",
        ]
        st.dataframe(df_sels, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune sélection. Baisse les seuils dans la sidebar.")

st.divider()

# ── COMBINÉS ─────────────────────────────────────────────────────────────────
st.subheader(f"🎯 Top {len(combos)} combinés")

if not combos:
    st.warning(
        "Aucun combiné généré. Essaie : "
        "↓ proba combinée min · ↓ proba modèle min · ↑ top N sélections."
    )
    st.stop()

for i, combo in enumerate(combos, 1):
    fold     = combo["fold"]
    prob     = combo["comb_prob"]
    uni_odds = combo["unibet_odds"]
    avg_edge = combo["avg_edge"]
    kly_pct  = combo["kelly_pct"]

    if prob >= 55:
        risk_icon, risk_lbl = "🟢", "Faible risque"
    elif prob >= 35:
        risk_icon, risk_lbl = "🟡", "Risque modéré"
    elif prob >= 20:
        risk_icon, risk_lbl = "🟠", "Risque élevé"
    else:
        risk_icon, risk_lbl = "🔴", "Très risqué"

    edge_str = f"+{avg_edge:.1f} %" if avg_edge >= 0 else f"{avg_edge:.1f} %"

    with st.container(border=True):
        h1, h2, h3, h4, h5, h6 = st.columns([0.4, 1.1, 1.5, 1.5, 1.5, 1.5])
        h1.markdown(f"### #{i}")
        h2.markdown(f"**{fold}-fold**  \n{risk_icon} {risk_lbl}")
        h3.metric("Proba combinée", f"{prob} %")
        h4.metric("Cote Unibet", f"{uni_odds:.2f}×")
        h5.metric("Edge moyen", edge_str)
        h6.metric("Kelly mise", f"{kly_pct:.1f} %")

        st.divider()

        for sel in combo["selections"]:
            c1, c2, c3, c4, c5 = st.columns([0.9, 2.5, 2, 1.3, 1.3])
            c1.caption(f"📅 {sel['kickoff']}")
            c2.markdown(f"**{sel['match']}**  \n`{sel['league']}`")
            c3.markdown(f"*{sel['market']}*  \n**→ {sel['outcome']}**")
            c4.markdown(f"Proba : **{sel['model_prob']} %**")
            c5.markdown(f"Cote : **{sel['unibet_odds']:.2f}**")

        st.divider()

        col_bankroll, col_sim = st.columns([1, 3])
        with col_bankroll:
            bankroll = st.number_input(
                "Bankroll (€)", min_value=10, max_value=100_000,
                value=100, step=10, key=f"bk_{i}",
            )
        with col_sim:
            mise       = round(bankroll * kly_pct / 100, 2)
            gain_brut  = round(mise * uni_odds, 2)
            gain_net   = round(gain_brut - mise, 2)
            st.markdown(
                f"💰 **Mise suggérée : {mise} €** · "
                f"Gain potentiel : **{gain_brut} €** (profit : **+{gain_net} €**)"
            )
            st.caption(
                f"Kelly 25 % · Meilleure cote marché : {combo['best_odds']:.2f}× · "
                f"EV moyen : {combo['avg_ev']:.3f}"
            )

st.divider()

# ── GUIDE ─────────────────────────────────────────────────────────────────────
with st.expander("ℹ️ Méthode et interprétation"):
    st.markdown(f"""
### Comment sont calculés les combinés

**Étape 1 — Probabilité consensus**
On récupère les cotes de tous les bookmakers disponibles, on retire leur marge individuelle,
puis on fait la moyenne. Résultat : la probabilité "juste" selon le marché.

**Étape 2 — Valeur espérée (EV)**
`EV = proba_modèle × cote_Unibet`
- EV > 1.0 → valeur positive (Unibet paie mieux que le marché)
- EV = 1.0 → prix juste
- EV < 1.0 → valeur négative

**Étape 3 — Score de sélection**
`Score = proba_modèle × EV` — favorise les sélections à la fois probables ET valorisées.

**Étape 4 — Combinés**
On prend le top {top_n_sels} sélections et on génère tous les combinés 2-{max_fold} folds possibles
(un seul match par fold pour éviter la corrélation). On classe par `proba × EV_moyen`.

**Kelly fractionnel (25 %)**
Mise optimale = bankroll × Kelly. On utilise 25 % du Kelly plein pour limiter le risque.
Un Kelly de 5 % sur 100 € → mise de 5 €, gain potentiel proportionnel à la cote.

**⚠️ Responsabilité**
Ces analyses sont indicatives. Les paris sportifs comportent des risques financiers réels.
Ne mise jamais plus que tu ne peux te permettre de perdre.
""")
