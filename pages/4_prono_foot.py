"""
FootMercato Pronostics v2
─────────────────────────
Stratégie d'extraction en 3 couches :
  1. API JSON interne FootMercato (endpoints détectés par inspection réseau)
  2. Scraping HTML + Playwright (JS rendu) si l'API échoue
  3. Scraping HTML statique classique en dernier recours

Sélection de date : aujourd'hui / demain / J+2 / date libre
Arbre de décision complet avec seuils configurables
"""

import re
import sys
import time
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import urljoin

sys.path.insert(0, ".")
from utils.auth import require_auth

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════
BASE_URL  = "https://www.footmercato.net"
LIVE_URL  = f"{BASE_URL}/live/"

# FootMercato expose une API interne — ces endpoints sont à confirmer/adapter
# via l'onglet Réseau de DevTools (filtre XHR/Fetch)
API_CALENDAR = f"{BASE_URL}/api/matches"          # endpoint probable pour le calendrier
API_MATCH    = f"{BASE_URL}/api/match/{{match_id}}"  # endpoint probable pour un match

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": BASE_URL,
}

HEADERS_API = {
    **HEADERS_BROWSER,
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}

REQUEST_TIMEOUT    = 20
MAX_WORKERS        = 10
PLAYWRIGHT_WORKERS = 4   # instances Chromium en parallèle (threading)
# Playwright est thread-safe si chaque thread crée sa propre instance sync_playwright().
# On évite multiprocessing/fork qui casse l'event-loop interne de Playwright sur macOS.

# ──────────────────────────────────────────────────────────────────────────────
# SEUILS ARBRE DE DÉCISION — ajustables dans la sidebar
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_THRESHOLDS = {
    "min_confidence":        35.0,   # confiance modèle minimale pour parier
    "min_proba_bet":         52.0,   # proba minimale de l'issue dominante
    "high_confidence_proba": 62.0,   # seuil "sûr"
    "premium_proba":         68.0,   # seuil "premium"
    "premium_gap":           15.0,   # écart min entre 1er et 2e issue
    "dc_min_proba":          58.0,   # proba min pour proposer un DC
    "min_sources":            1,     # nombre minimum de sources non-nulles
}

WEIGHTS = {
    "site_pre_match":  0.35,
    "odds":            0.22,   # cotes bookmakers (FootMercato ou Odds API)
    "community_prono": 0.09,
    "form":            0.09,
    "h2h":             0.05,
    "api_football":    0.12,   # prédictions API-Football (si clé fournie)
    "odds_ext":        0.08,   # cotes Odds API indépendantes (si clé fournie)
}

# ──────────────────────────────────────────────────────────────────────────────
# 5 GRANDS CHAMPIONNATS
# ──────────────────────────────────────────────────────────────────────────────
MAJOR_LEAGUE_KEYWORDS = [
    "premier league", "fa premier", "england",
    "la liga", "primera division", "laliga", "spain", "espagne",
    "bundesliga", "germany", "allemagne",
    "serie a", "serie-a", "italy", "italie",
    "ligue 1", "ligue un", "ligue1", "france",
]

MAJOR_LEAGUE_AF_IDS = [39, 78, 135, 140, 61]   # PL, Bundesliga, Serie A, La Liga, Ligue 1

ODDS_API_SPORTS = [
    "soccer_epl", "soccer_germany_bundesliga",
    "soccer_italy_serie_a", "soccer_spain_la_liga", "soccer_france_ligue_one",
]

FORM_POINTS = {"V": 3, "N": 1, "D": 0}

# ══════════════════════════════════════════════════════════════════════════════
# DATACLASS
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class MatchRow:
    competition: str = ""
    home_team:   str = ""
    away_team:   str = ""
    kickoff:     str = ""
    match_url:   str = ""
    match_id:    str = ""
    raw_text:    str = ""


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════
def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def safe_get(url: str, headers=None, params=None, retries=2) -> Optional[requests.Response]:
    h = headers or HEADERS_BROWSER
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=h, params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    return None

def _section(text: str, *labels, window=800) -> str:
    for label in labels:
        idx = text.find(label)
        if idx != -1:
            return text[idx: idx + window]
    return ""

def pct_triplet(text: str, tolerance=8) -> Optional[Tuple[float, float, float]]:
    pcts = re.findall(r"(\d{1,3})\s*%", text)
    for i in range(len(pcts) - 2):
        a, b, c = map(int, pcts[i:i+3])
        if 100 - tolerance <= a + b + c <= 100 + tolerance:
            return float(a), float(b), float(c)
    return None

def normalize_triplet(a, b, c) -> Tuple[float, float, float]:
    t = a + b + c
    if t <= 0:
        return 33.33, 33.33, 33.34
    return 100*a/t, 100*b/t, 100*c/t

def odds_to_prob(odds: Tuple) -> Tuple[float, float, float]:
    inv = [1/o for o in odds]
    t   = sum(inv)
    return tuple(round(100*i/t, 2) for i in inv)  # type: ignore

def score_form(series: List[str]) -> float:
    if not series:
        return 0.0
    return sum(FORM_POINTS.get(x, 0) for x in series) / (3 * len(series))

def form_to_triplet(home: List[str], away: List[str]) -> Tuple[float, float, float]:
    diff = score_form(home) - score_form(away)
    h = max(0.05, 0.36 + 0.25 * diff)
    a = max(0.05, 0.30 - 0.25 * diff)
    d = max(0.10, 0.34 - 0.05 * abs(diff))
    return normalize_triplet(h, d, a)


# ══════════════════════════════════════════════════════════════════════════════
# COUCHE 1 : TENTATIVE API JSON
# ══════════════════════════════════════════════════════════════════════════════
def try_api_calendar(target_date: date) -> Optional[List[Dict]]:
    """
    Tente de récupérer le calendrier via l'API JSON interne.
    FootMercato utilise probablement une URL du type :
      /api/matches?date=2025-04-19
    ou expose les données dans un <script id="__NEXT_DATA__"> (Next.js).
    
    Retourne une liste de dicts matchs ou None si l'API n'est pas accessible.
    """
    date_str = target_date.strftime("%Y-%m-%d")

    # ── Tentative Next.js __NEXT_DATA__ ──────────────────────────────────
    url = f"{LIVE_URL}?date={date_str}"
    r = safe_get(url)
    if r:
        soup = BeautifulSoup(r.text, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            try:
                data = json.loads(script.string)
                # Chercher les matchs dans la structure Next.js
                matches = _extract_from_nextjs(data)
                if matches:
                    return matches
            except (json.JSONDecodeError, KeyError):
                pass

    # ── Tentative API REST directe ────────────────────────────────────────
    for endpoint in [
        f"{BASE_URL}/api/matches",
        f"{BASE_URL}/api/live",
        f"{BASE_URL}/api/calendar",
    ]:
        r = safe_get(endpoint, headers=HEADERS_API, params={"date": date_str})
        if r:
            try:
                data = r.json()
                if isinstance(data, list) and data:
                    return data
                if isinstance(data, dict) and ("matches" in data or "data" in data):
                    return data.get("matches") or data.get("data") or []
            except (json.JSONDecodeError, ValueError):
                pass

    return None


def _extract_from_nextjs(data: Dict) -> Optional[List[Dict]]:
    """Cherche récursivement les matchs dans la structure __NEXT_DATA__."""
    def _search(obj, depth=0):
        if depth > 8:
            return None
        if isinstance(obj, list):
            # Cherche une liste de matchs (contient home_team / homeTeam / equipe_dom)
            if len(obj) > 0 and isinstance(obj[0], dict):
                keys = set(obj[0].keys())
                match_keys = {"homeTeam", "home_team", "equipe_dom", "domicile", "home"}
                if keys & match_keys:
                    return obj
            for item in obj:
                r = _search(item, depth+1)
                if r:
                    return r
        elif isinstance(obj, dict):
            # Cherche des clés typiques
            for key in ("matches", "data", "liveMatches", "calendar", "fixtures"):
                if key in obj:
                    r = _search(obj[key], depth+1)
                    if r:
                        return r
            for v in obj.values():
                r = _search(v, depth+1)
                if r:
                    return r
        return None
    return _search(data)


def normalize_api_match(raw: Dict) -> Optional[MatchRow]:
    """Normalise un match retourné par l'API JSON."""
    def get(*keys):
        for k in keys:
            if k in raw and raw[k]:
                return str(raw[k]).strip()
        return ""

    home = get("homeTeam", "home_team", "domicile", "home", "equipe_dom")
    away = get("awayTeam", "away_team", "exterieur", "away", "equipe_ext")
    if not home or not away:
        return None

    comp    = get("competition", "league", "competitionName", "ligue")
    kickoff = get("time", "kickoff", "heure", "matchTime", "startTime")
    mid     = get("id", "matchId", "match_id")
    url     = get("url", "matchUrl", "link")
    if not url and mid:
        url = f"{BASE_URL}/live/{mid}"

    return MatchRow(
        competition=comp,
        home_team=home,
        away_team=away,
        kickoff=kickoff[:5] if kickoff else "",
        match_url=url or "",
        match_id=mid,
    )


# ══════════════════════════════════════════════════════════════════════════════
# COUCHE 2 : SCRAPING HTML (statique + enrichissement)
# ══════════════════════════════════════════════════════════════════════════════
def build_live_url(target_date: date) -> str:
    """FootMercato accepte ?date=YYYY-MM-DD ou /live/YYYY-MM-DD/"""
    today = date.today()
    if target_date == today:
        return LIVE_URL
    date_str = target_date.strftime("%Y-%m-%d")
    return f"{LIVE_URL}?date={date_str}"


# ── Détection Playwright ──────────────────────────────────────────────────────
def _playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False

PLAYWRIGHT_OK = _playwright_available()


def _fetch_requests(url: str) -> Optional[str]:
    """Fetch simple via requests — HTML statique uniquement."""
    r = safe_get(url)
    return r.text if r else None


def _fetch_playwright(url: str) -> Optional[str]:
    """
    Fetch avec Chromium headless — exécute le JS, attend la fin des XHR.
    Intercepte les réponses JSON et les stocke dans st.session_state["xhr_cache"]
    pour qu'on puisse y piocher les données d'analyse sans refetcher.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return _fetch_requests(url)

    xhr_store: Dict[str, str] = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=HEADERS_BROWSER["User-Agent"],
                locale="fr-FR",
                extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"},
            )
            page = ctx.new_page()

            # Intercepte toutes les réponses JSON (XHR/Fetch)
            def _on_response(response):
                if "json" in response.headers.get("content-type", "") and response.status == 200:
                    try:
                        body = response.text()
                        if body and len(body) > 30:
                            xhr_store[response.url] = body
                    except Exception:
                        pass

            page.on("response", _on_response)

            try:
                page.goto(url, wait_until="networkidle", timeout=35_000)
            except PWTimeout:
                pass  # on prend ce qu'on a

            page.wait_for_timeout(1500)   # laisse les XHR tardifs arriver
            html = page.content()
            browser.close()

        # Injecte les réponses XHR capturées directement dans le HTML
        # pour qu'elles soient disponibles dans analyse_match via BeautifulSoup
        if xhr_store:
            xhr_blob = json.dumps(list(xhr_store.values()), ensure_ascii=False)
            injection = f'<script id="__XHR_DATA__">{xhr_blob}</script>'
            html = html.replace("</body>", injection + "</body>") if "</body>" in html else html + injection

        return html

    except Exception:
        return _fetch_requests(url)   # fallback silencieux


@st.cache_data(ttl=600, show_spinner=False)
def fetch_page(url: str, use_playwright: bool = False) -> Optional[str]:
    """
    Point d'entrée unique.
    use_playwright=True  → Chromium headless (JS rendu, données dynamiques)
    use_playwright=False → requests classique (rapide, HTML statique)
    """
    if use_playwright and PLAYWRIGHT_OK:
        return _fetch_playwright(url)
    return _fetch_requests(url)


def is_competition_label(text: str) -> bool:
    text = normalize(text)
    if not text or len(text) < 4:
        return False
    bad = ("Menu","Rechercher","Filtrer","Compétitions","Zone","Chaine",
           "Live","Tous","Aujourd","Hier","Demain","Buteurs","Classement",
           "Calendrier","La suite","Comment suivre","publicité")
    if any(text.startswith(b) for b in bad):
        return False
    if re.search(r"\b\d{1,2}:\d{2}\b|\bMT\b|\bterminé\b|\bBonus\b", text, re.I):
        return False
    good = ("Ligue","League","Bundesliga","Liga","Serie","National","Cup","Coupe",
            "Division","Championship","MLS","Soccer","Super League","Pro League",
            "CAF","Champions","Euro","U19","U21","femmes","Eliminatoires","Ekstraklasa")
    return any(g.lower() in text.lower() for g in good) or len(text) >= 5


def extract_match_id(href: str) -> str:
    m = re.search(r"/live/(\d+)", href)
    return m.group(1) if m else ""


@st.cache_data(ttl=600, show_spinner=False)
def enrich_from_detail_page(match_url: str, use_playwright: bool = False) -> Tuple[str, str, str]:
    """Retourne (competition, home, away) depuis la page détail."""
    html = fetch_page(match_url, use_playwright=use_playwright)
    if not html:
        return "", "", ""
    soup = BeautifulSoup(html, "html.parser")
    text = normalize(soup.get_text(" ", strip=True))

    comp = home = away = ""

    # ── Patterns regex sur le texte brut ─────────────────────────────────
    for pat in [r"Compétition\s+(.+?)\s+Saison", r"Ligue\s*:\s*(.+?)\s*\|"]:
        m = re.search(pat, text)
        if m:
            comp = normalize(m.group(1))
            break

    m = re.search(
        r"Équipe à domicile\s+(.+?)\s+Équipe à l'extérieur\s+(.+?)\s+"
        r"(?:Résultats|Saison|Arbitre|Stade|Classement)",
        text,
    )
    if m:
        home, away = normalize(m.group(1)), normalize(m.group(2))

    # ── og:title / title ──────────────────────────────────────────────────
    if not home or not away:
        for el in [soup.find("meta", property="og:title"), soup.title]:
            val = normalize(el.get("content", "") if el and el.name == "meta" else (el.get_text() if el else ""))
            m = re.search(r"(.+?)\s+(?:vs\.?|contre|-)\s+(.+?)(?:\s+[-|]|$)", val, re.I)
            if m:
                home = home or normalize(m.group(1))
                away = away or normalize(m.group(2))
                break

    # ── Sélecteurs CSS FootMercato ────────────────────────────────────────
    if not home or not away:
        css_pairs = [
            (".match-header__team--home .team-name", ".match-header__team--away .team-name"),
            (".home-team .name", ".away-team .name"),
            ("[class*='home'] [class*='team-name']", "[class*='away'] [class*='team-name']"),
            ("h1", None),   # fallback : h1 contient souvent "Home vs Away"
        ]
        for sel_h, sel_a in css_pairs:
            el_h = soup.select_one(sel_h)
            if el_h and sel_a:
                el_a = soup.select_one(sel_a)
                if el_a:
                    home = home or normalize(el_h.get_text())
                    away = away or normalize(el_a.get_text())
                    break
            elif el_h:
                val = normalize(el_h.get_text())
                m = re.search(r"(.+?)\s+(?:vs\.?|-)\s+(.+)", val, re.I)
                if m:
                    home = home or normalize(m.group(1))
                    away = away or normalize(m.group(2))
                    break

    return comp, home, away


def extract_matches_html(html: str, target_date: date) -> List[MatchRow]:
    """Extraction depuis le HTML statique de la page live."""
    soup = BeautifulSoup(html, "html.parser")
    matches: List[MatchRow] = []
    seen: set = set()
    current_comp = ""

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = normalize(a.get_text(" ", strip=True))

        if "/live/" not in href:
            if is_competition_label(text):
                current_comp = text
            continue

        mid = extract_match_id(href)
        if not mid:
            continue

        url = urljoin(BASE_URL, href)
        if url in seen or "adsrv" in url.lower() or "Bonus" in text:
            continue

        kickoff = ""
        m = re.search(r"\b(\d{1,2}:\d{2})\b", text)
        if m:
            kickoff = m.group(1)

        # Nettoyage texte pour les équipes (sera écrasé par l'enrichissement)
        cleaned = re.sub(r"\b\d{1,2}:\d{2}\b|\bMT\b|\bterminé\b|\b\d{1,3}'(?:\+\d+)?\b|\b\d+\b",
                         "", text, flags=re.I)
        cleaned = normalize(cleaned)
        words = cleaned.split()
        mid_idx = max(1, len(words) // 2)
        home_guess = " ".join(words[:mid_idx])
        away_guess = " ".join(words[mid_idx:])

        matches.append(MatchRow(
            competition=current_comp,
            home_team=home_guess,
            away_team=away_guess,
            kickoff=kickoff,
            match_url=url,
            match_id=mid,
            raw_text=text,
        ))
        seen.add(url)

    return matches


def enrich_matches_parallel(matches: List[MatchRow], use_playwright: bool = False) -> List[MatchRow]:
    """
    Enrichit les matchs en parallèle (pure, sans appel Streamlit).
    Avec Playwright : chaque page est rendue en JS → données complètes.
    ATTENTION : Playwright n'est pas thread-safe → on limite MAX_WORKERS=1 dans ce cas.
    """
    workers = 1 if use_playwright else MAX_WORKERS

    def _enrich(match: MatchRow) -> MatchRow:
        comp, home, away = enrich_from_detail_page(match.match_url, use_playwright=use_playwright)
        if comp:  match.competition = comp
        if home:  match.home_team   = home
        if away:  match.away_team   = away
        return match

    results: List[MatchRow] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_enrich, m): m for m in matches}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception:
                results.append(futures[future])  # garde le match non-enrichi

    return [m for m in results if m.home_team and m.away_team]


# ══════════════════════════════════════════════════════════════════════════════
# PARSING DONNÉES ANALYSE (probabilités, cotes, forme, H2H)
# ══════════════════════════════════════════════════════════════════════════════
def parse_pre_match(text: str) -> Optional[Tuple]:
    sub = _section(text, "Probabilité de victoire", "Proba de victoire", "Probabilités")
    return pct_triplet(sub) if sub else None

def parse_community(text: str) -> Optional[Tuple]:
    sub = _section(text, "Qui va gagner", "Pronostic communauté", "Pronostics des membres")
    return pct_triplet(sub) if sub else None

def parse_h2h(text: str) -> Optional[Tuple]:
    sub = _section(text, "Rencontres précédentes", "Face à face", "H2H")
    return pct_triplet(sub) if sub else None

def parse_odds(text: str) -> Optional[Tuple[float, float, float]]:
    sub = _section(text, "Côtes du match", "Cotes du match", "Cotes", window=500)
    if not sub:
        return None
    # Pattern principal
    m = re.search(
        r"1\s+([0-9]+[.,][0-9]+)\s+N\s+([0-9]+[.,][0-9]+)\s+2\s+([0-9]+[.,][0-9]+)",
        sub,
    )
    if m:
        o1, ox, o2 = [float(x.replace(",", ".")) for x in m.groups()]
        if all(1.01 < x < 50 for x in (o1, ox, o2)):
            return o1, ox, o2
    # Fallback : 3 flottants consécutifs plausibles
    nums = re.findall(r"([1-9]\d*[.,]\d{2})", sub)
    if len(nums) >= 3:
        try:
            o1, ox, o2 = [float(n.replace(",", ".")) for n in nums[:3]]
            if all(1.01 < x < 50 for x in (o1, ox, o2)):
                return o1, ox, o2
        except ValueError:
            pass
    return None

def parse_form(text: str) -> Tuple[List[str], List[str]]:
    idx = text.find("Série en cours")
    if idx == -1:
        idx = text.find("Forme récente")
    if idx == -1:
        return [], []
    sub     = text[idx: idx + 1500]
    letters = re.findall(r"\b([VND])\b", sub)[:10]
    return letters[:5], letters[5:10]


# ══════════════════════════════════════════════════════════════════════════════
# PONDÉRATION ET CONFIANCE
# ══════════════════════════════════════════════════════════════════════════════
def weighted_triplet(sources: Dict[str, Optional[Tuple]]) -> Tuple[float, float, float, float, int]:
    active = [(k, v) for k, v in sources.items() if v is not None]
    if not active:
        return 33.33, 33.33, 33.34, 0.0, 0

    h = d = a = total_w = 0.0
    for key, tri in active:
        w = WEIGHTS.get(key, 0.0)
        total_w += w
        h += tri[0] * w
        d += tri[1] * w
        a += tri[2] * w

    h, d, a  = normalize_triplet(h, d, a)
    coverage = min(total_w / sum(WEIGHTS.values()), 1.0)

    triplets  = [v for _, v in active]
    max_spread = 0.0
    if len(triplets) >= 2:
        for i in range(len(triplets)):
            for j in range(i+1, len(triplets)):
                sp = sum(abs(triplets[i][k] - triplets[j][k]) for k in range(3)) / 3
                max_spread = max(max_spread, sp)
    consensus = max(0.0, 1.0 - max_spread / 35.0)

    confidence = round(100 * (0.60 * coverage + 0.40 * consensus), 1)
    return round(h, 2), round(d, 2), round(a, 2), confidence, len(active)


# ══════════════════════════════════════════════════════════════════════════════
# ARBRE DE DÉCISION
# ══════════════════════════════════════════════════════════════════════════════
def decision_tree(
    p1: float, px: float, p2: float,
    confidence: float,
    n_sources: int,
    home: str, away: str,
    thresholds: Dict,
) -> Dict:
    result = _decision_tree_inner(p1, px, p2, confidence, n_sources, home, away, thresholds)
    result["action"] = _compute_action(result["niveau"], confidence, n_sources)
    return result


def _decision_tree_inner(
    p1: float, px: float, p2: float,
    confidence: float,
    n_sources: int,
    home: str, away: str,
    thresholds: Dict,
) -> Dict:
    T = thresholds
    no_bet = {
        "signal": "—", "signal_type": "SKIP",
        "signal_proba": 0.0, "niveau": "🔴 SKIP", "explication": "",
    }

    # ── 0. Données insuffisantes ──────────────────────────────────────────
    if n_sources < T["min_sources"]:
        return {**no_bet, "explication": "Aucune source de données disponible."}
    if confidence < T["min_confidence"]:
        return {**no_bet,
                "explication": f"Confiance trop faible ({confidence:.0f} % < {T['min_confidence']:.0f} %)."}

    vals  = {"1": p1, "N": px, "2": p2}
    best  = max(vals, key=vals.get)
    bp    = vals[best]
    snd_p = sorted(vals.values(), reverse=True)[1]
    gap   = bp - snd_p
    fav   = home if best == "1" else (away if best == "2" else "Nul")

    # ── 1. Trop incertain → DC ? ──────────────────────────────────────────
    if bp < T["min_proba_bet"]:
        dc_map = {"1": ("1N", p1+px), "N": ("12", p1+p2), "2": ("X2", p2+px)}
        dc_key, dc_p = dc_map[best]
        if dc_p >= T["dc_min_proba"] and confidence >= T["min_confidence"]:
            return {
                "signal":       f"DC {dc_key}",
                "signal_type":  dc_key,
                "signal_proba": round(dc_p, 2),
                "niveau":       "🟡 Prudent",
                "explication":  (
                    f"Issue nette absente ({bp:.1f} %). "
                    f"DC {dc_key} à {dc_p:.1f} % recommandée (couverture 2 issues sur 3)."
                ),
            }
        return {**no_bet,
                "explication": f"Match trop équilibré ({bp:.1f} %). Pas d'edge identifiable."}

    # ── 2. Nul dominant → DNB ─────────────────────────────────────────────
    if best == "N":
        if p1 >= p2:
            return {
                "signal":       f"DNB Domicile ({home})",
                "signal_type":  "DNB_1",
                "signal_proba": round(p1+p2, 2),
                "niveau":       "🟡 Prudent",
                "explication":  (
                    f"Nul probable ({px:.1f} %). "
                    f"DNB domicile ({home}) : remboursé si nul, gagnant si victoire dom."
                ),
            }
        return {
            "signal":       f"DNB Extérieur ({away})",
            "signal_type":  "DNB_2",
            "signal_proba": round(p1+p2, 2),
            "niveau":       "🟡 Prudent",
            "explication":  (
                f"Nul probable ({px:.1f} %). "
                f"DNB extérieur ({away}) : remboursé si nul, gagnant si victoire ext."
            ),
        }

    # ── 3. Issue dominante 1 ou 2 ─────────────────────────────────────────
    label = f"Victoire {'Domicile' if best=='1' else 'Extérieur'} ({fav})"

    if (bp >= T["premium_proba"] and gap >= T["premium_gap"] and confidence >= 60):
        niveau = "⭐ Premium"
    elif (bp >= T["high_confidence_proba"] or (gap >= 10 and confidence >= 50)):
        niveau = "🟢 Sûr"
    else:
        niveau = "🟡 Prudent"

    return {
        "signal":       label,
        "signal_type":  best,
        "signal_proba": bp,
        "niveau":       niveau,
        "explication":  (
            f"{fav} favori à {bp:.1f} % "
            f"(écart {gap:.1f} pts, {n_sources} source(s), confiance {confidence:.0f} %)."
        ),
    }


def implied_events(p1, px, p2) -> Dict:
    nd = max(p1+p2, 1e-6)
    return {
        "DC_1N": round(p1+px, 2),
        "DC_X2": round(p2+px, 2),
        "DC_12": round(p1+p2, 2),
        "DNB_1": round(100*p1/nd, 2),
        "DNB_2": round(100*p2/nd, 2),
    }


def _compute_action(niveau: str, confidence: float, n_sources: int) -> str:
    """Traduit (niveau, confiance, sources) en conseil de mise selon la grille complète."""
    if niveau == "🔴 SKIP":
        return "🚫 Jamais"
    if niveau == "⭐ Premium":
        return "✅ Mise pleine" if n_sources >= 3 else "⚠️ Mise réduite — peu de sources"
    if niveau == "🟢 Sûr":
        if n_sources >= 2 and confidence >= 50:
            return "✅ Mise normale"
        if n_sources >= 2:
            return "⚠️ Mise réduite"
        return "🚫 Passer"
    if niveau == "🟡 Prudent":
        return "⚠️ Petite mise ou DC/DNB" if (confidence >= 50 and n_sources >= 3) else "🚫 Passer"
    return "🚫 Jamais"


def estimate_goals(p1: float, px: float, p2: float) -> Dict:
    """
    Marchés buts via modèle Poisson calibré sur le football européen (~2.65 buts/match).
    Plus le favori est dominant → lambda plus élevé.
    Plus la proba de nul est haute → lambda plus faible.
    """
    import math
    max_p  = max(p1, p2) / 100.0
    lam    = max(1.0, min(4.5, 2.3 + 1.4 * (max_p - 1 / 3)))
    ratio_h = p1 / max(p1 + p2, 1e-6)
    lam_h  = lam * (0.38 + 0.42 * ratio_h)
    lam_a  = lam - lam_h

    def _over(k: int, l: float) -> float:
        cdf = sum(math.exp(-l) * l**i / math.factorial(i) for i in range(k + 1))
        return round((1 - cdf) * 100, 1)

    btts = round((1 - math.exp(-lam_h)) * (1 - math.exp(-lam_a)) * 100, 1)
    return {
        "buts_esp_dom":   round(lam_h, 2),
        "buts_esp_ext":   round(lam_a, 2),
        "buts_esp_total": round(lam, 2),
        "over_05":  _over(0, lam),
        "over_15":  _over(1, lam),
        "over_25":  _over(2, lam),
        "over_35":  _over(3, lam),
        "over_45":  _over(4, lam),
        "under_15": round(100 - _over(1, lam), 1),
        "under_25": round(100 - _over(2, lam), 1),
        "under_35": round(100 - _over(3, lam), 1),
        "btts_oui": btts,
        "btts_non": round(100 - btts, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSE D'UN MATCH
# ══════════════════════════════════════════════════════════════════════════════
EMPTY_ANALYSIS = {
    "site_pre_match_1": None, "site_pre_match_X": None, "site_pre_match_2": None,
    "community_1": None, "community_X": None, "community_2": None,
    "h2h_1": None, "h2h_X": None, "h2h_2": None,
    "form_1": None, "form_X": None, "form_2": None,
    "odds_1": None, "odds_X": None, "odds_2": None,
    "serie_dom": None, "serie_ext": None,
    "proba_1": None, "proba_X": None, "proba_2": None,
    "confiance": 0.0, "n_sources": 0,
    "DC_1N": None, "DC_X2": None, "DC_12": None,
    "DNB_1": None, "DNB_2": None,
    "signal": "—", "signal_type": "SKIP", "action": "🚫 Jamais",
    "signal_proba": 0.0, "niveau": "🔴 SKIP", "explication": "Pas de données.",
    # Marchés buts
    "buts_esp_dom": None, "buts_esp_ext": None, "buts_esp_total": None,
    "over_05": None, "over_15": None, "over_25": None, "over_35": None, "over_45": None,
    "under_15": None, "under_25": None, "under_35": None,
    "btts_oui": None, "btts_non": None,
}


@st.cache_data(ttl=600, show_spinner=False)
def analyse_match(match_url: str, home: str, away: str, thresholds_hash: str, use_playwright: bool = False) -> Dict:
    """
    thresholds_hash est passé pour invalider le cache si les seuils changent.
    """
    html = fetch_page(match_url, use_playwright=use_playwright)
    if not html:
        return {**EMPTY_ANALYSIS}

    soup = BeautifulSoup(html, "html.parser")
    text = normalize(soup.get_text(" ", strip=True))

    # ── Tentative API JSON intégrée dans la page (Next.js) ────────────────
    json_sources: Dict[str, Optional[Tuple]] = {}
    script = soup.find("script", id="__NEXT_DATA__")
    if script and script.string:
        try:
            nd = json.loads(script.string)
            json_sources = _extract_probabilities_from_json(nd)
        except (json.JSONDecodeError, KeyError):
            pass

    # ── Données XHR interceptées par Playwright (injectées dans le HTML) ──
    xhr_script = soup.find("script", id="__XHR_DATA__")
    if xhr_script and xhr_script.string:
        try:
            xhr_list = json.loads(xhr_script.string)
            for xhr_raw in xhr_list:
                if not json_sources.get("site_pre_match") or not json_sources.get("odds_raw"):
                    try:
                        xhr_obj = json.loads(xhr_raw) if isinstance(xhr_raw, str) else xhr_raw
                        probs = _extract_probabilities_from_json(xhr_obj)
                        for k, v in probs.items():
                            if v is not None and k not in json_sources:
                                json_sources[k] = v
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        pass
        except (json.JSONDecodeError, TypeError):
            pass

    # ── Parsing HTML classique ────────────────────────────────────────────
    pre_match   = json_sources.get("site_pre_match") or parse_pre_match(text)
    community   = json_sources.get("community_prono") or parse_community(text)
    h2h         = json_sources.get("h2h")             or parse_h2h(text)
    odds_raw    = json_sources.get("odds_raw")         or parse_odds(text)
    odds_probs  = odds_to_prob(odds_raw) if odds_raw else None

    home_ser, away_ser = parse_form(text)
    form_tri = form_to_triplet(home_ser, away_ser) if (home_ser or away_ser) else None

    sources = {
        "site_pre_match":  pre_match,
        "odds":            odds_probs,
        "community_prono": community,
        "form":            form_tri,
        "h2h":             h2h,
    }

    p1, px, p2, conf, n_src = weighted_triplet(sources)
    events = implied_events(p1, px, p2)

    # Thresholds depuis hash (on passe les seuils par défaut ici)
    tree  = decision_tree(p1, px, p2, conf, n_src, home, away, DEFAULT_THRESHOLDS)
    goals = estimate_goals(p1, px, p2)

    def _r(t, i): return round(t[i], 2) if t else None

    return {
        "site_pre_match_1": _r(pre_match, 0),
        "site_pre_match_X": _r(pre_match, 1),
        "site_pre_match_2": _r(pre_match, 2),
        "community_1": _r(community, 0),
        "community_X": _r(community, 1),
        "community_2": _r(community, 2),
        "h2h_1": _r(h2h, 0), "h2h_X": _r(h2h, 1), "h2h_2": _r(h2h, 2),
        "form_1": _r(form_tri, 0), "form_X": _r(form_tri, 1), "form_2": _r(form_tri, 2),
        "odds_1": _r(odds_probs, 0), "odds_X": _r(odds_probs, 1), "odds_2": _r(odds_probs, 2),
        "serie_dom": "".join(home_ser) or None,
        "serie_ext": "".join(away_ser) or None,
        "proba_1": p1, "proba_X": px, "proba_2": p2,
        "confiance": conf, "n_sources": n_src,
        **events, **tree, **goals,
    }


def _extract_probabilities_from_json(data: Dict) -> Dict[str, Optional[Tuple]]:
    """
    Cherche récursivement les triplets de probabilités dans __NEXT_DATA__.
    Retourne un dict de triplets nommés.
    """
    result: Dict[str, Optional[Tuple]] = {}
    text = json.dumps(data)

    # Cherche des patterns JSON comme "homeWin":45,"draw":30,"awayWin":25
    patterns = [
        (r'"homeWin"\s*:\s*(\d+(?:\.\d+)?),\s*"draw"\s*:\s*(\d+(?:\.\d+)?),\s*"awayWin"\s*:\s*(\d+(?:\.\d+)?)', "site_pre_match"),
        (r'"home"\s*:\s*(\d+(?:\.\d+)?),\s*"draw"\s*:\s*(\d+(?:\.\d+)?),\s*"away"\s*:\s*(\d+(?:\.\d+)?)', "site_pre_match"),
        (r'"probaHome"\s*:\s*(\d+(?:\.\d+)?),\s*"probaDraw"\s*:\s*(\d+(?:\.\d+)?),\s*"probaAway"\s*:\s*(\d+(?:\.\d+)?)', "site_pre_match"),
        (r'"odd1"\s*:\s*"?([0-9.]+)"?,\s*"oddX"\s*:\s*"?([0-9.]+)"?,\s*"odd2"\s*:\s*"?([0-9.]+)"?', "odds_raw"),
        (r'"oddsHome"\s*:\s*"?([0-9.]+)"?,\s*"oddsDraw"\s*:\s*"?([0-9.]+)"?,\s*"oddsAway"\s*:\s*"?([0-9.]+)"?', "odds_raw"),
    ]

    for pat, key in patterns:
        if key in result:
            continue
        m = re.search(pat, text)
        if m:
            a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
            result[key] = (a, b, c)

    # ── Recherche générique dans les listes JSON (tableau de 3 nombres ~= proba) ──
    if "site_pre_match" not in result:
        # Cherche des triplets [h, d, a] ou {h, d, a} dont la somme ≈ 100
        triplet_pats = [
            r'"(?:proba(?:Home|Dom|1)|win(?:Home|1)|home(?:Win|Proba))"\s*:\s*(\d+(?:\.\d+)?)',
            r'"(?:proba(?:Draw|Nul|X)|draw(?:Proba)?|nul)"\s*:\s*(\d+(?:\.\d+)?)',
            r'"(?:proba(?:Away|Ext|2)|win(?:Away|2)|away(?:Win|Proba))"\s*:\s*(\d+(?:\.\d+)?)',
        ]
        nums = []
        for p in triplet_pats:
            fm = re.search(p, text, re.IGNORECASE)
            nums.append(float(fm.group(1)) if fm else None)
        if all(n is not None for n in nums):
            a, b, c = nums[0], nums[1], nums[2]  # type: ignore
            if 80 <= a + b + c <= 120:
                result["site_pre_match"] = (a, b, c)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# SOURCES EXTERNES — API-Football + The Odds API
# ══════════════════════════════════════════════════════════════════════════════

def _norm_team(name: str) -> str:
    import unicodedata
    n = name.lower().strip()
    n = "".join(c for c in unicodedata.normalize("NFD", n) if unicodedata.category(c) != "Mn")
    for s in (" fc", " cf", " sc", " ac", " afc", " fk", " sk", " 1.", " vfb", " vfl", " tsv"):
        n = n.replace(s, "")
    return n.strip()

def _sim(a: str, b: str) -> float:
    a, b = _norm_team(a), _norm_team(b)
    if a == b:              return 1.0
    if a in b or b in a:   return 0.85
    ta, tb = set(a.split()), set(b.split())
    return len(ta & tb) / max(len(ta | tb), 1)

def _match_score(h1: str, a1: str, h2: str, a2: str) -> float:
    return (_sim(h1, h2) + _sim(a1, a2)) / 2

def _row_triplet(row: "pd.Series", col_prefix: str) -> Optional[Tuple[float, float, float]]:
    """Reconstruit un triplet depuis les colonnes _1/_X/_2 du DataFrame."""
    v1 = row.get(f"{col_prefix}_1")
    vx = row.get(f"{col_prefix}_X")
    v2 = row.get(f"{col_prefix}_2")
    try:
        if v1 is not None and not pd.isna(v1):
            return (float(v1), float(vx or 33.33), float(v2 or 33.33))
    except Exception:
        pass
    return None

@st.cache_data(ttl=600, show_spinner=False)
def _fetch_af_fixtures(date_str: str, api_key: str) -> List[Dict]:
    """Récupère les matchs des 5 grands championnats via API-Football (5 appels max)."""
    if not api_key:
        return []
    season = date_str[:4]
    hdrs = {"x-rapidapi-key": api_key, "x-rapidapi-host": "v3.football.api-sports.io"}
    fixtures: List[Dict] = []
    for lid in MAJOR_LEAGUE_AF_IDS:
        r = safe_get("https://v3.football.api-sports.io/fixtures",
                     headers=hdrs, params={"date": date_str, "league": lid, "season": season})
        if r:
            try:
                fixtures.extend(r.json().get("response", []))
            except Exception:
                pass
        time.sleep(0.15)
    return fixtures

@st.cache_data(ttl=600, show_spinner=False)
def _fetch_af_prediction(fixture_id: int, api_key: str) -> Optional[Dict]:
    """Prédiction API-Football pour un fixture (1 appel)."""
    if not api_key:
        return None
    hdrs = {"x-rapidapi-key": api_key, "x-rapidapi-host": "v3.football.api-sports.io"}
    r = safe_get("https://v3.football.api-sports.io/predictions",
                 headers=hdrs, params={"fixture": fixture_id})
    if r:
        try:
            resp = r.json().get("response", [])
            return resp[0] if resp else None
        except Exception:
            pass
    return None

def _parse_af_probs(pred: Dict) -> Optional[Tuple[float, float, float]]:
    try:
        pct = pred.get("predictions", {}).get("percent", {})
        h = float(pct.get("home", "0").replace("%", ""))
        d = float(pct.get("draw", "0").replace("%", ""))
        a = float(pct.get("away", "0").replace("%", ""))
        if h + d + a > 0:
            return normalize_triplet(h, d, a)
    except Exception:
        pass
    return None

def _parse_af_form(pred: Dict) -> Tuple[List[str], List[str]]:
    MAP = {"W": "V", "D": "N", "L": "D"}
    def _conv(s: str) -> List[str]:
        return [MAP[c] for c in (s or "") if c in MAP][-5:]
    try:
        teams = pred.get("teams", {})
        hf = teams.get("home", {}).get("league", {}).get("form", "")
        af = teams.get("away", {}).get("league", {}).get("form", "")
        return _conv(hf), _conv(af)
    except Exception:
        return [], []

def _parse_af_h2h(pred: Dict) -> Optional[Tuple[float, float, float]]:
    try:
        h2h = pred.get("h2h", [])
        if len(h2h) < 3:
            return None
        home_id = pred.get("teams", {}).get("home", {}).get("id")
        wins_h = sum(1 for g in h2h if g.get("teams", {}).get("home", {}).get("winner") and
                     g["teams"]["home"]["id"] == home_id)
        wins_a = sum(1 for g in h2h if g.get("teams", {}).get("away", {}).get("winner") and
                     g["teams"]["away"]["id"] != home_id)
        draws  = len(h2h) - wins_h - wins_a
        t = len(h2h)
        return normalize_triplet(wins_h/t*100, draws/t*100, wins_a/t*100)
    except Exception:
        return None

@st.cache_data(ttl=600, show_spinner=False)
def _fetch_odds_api_games(date_str: str, api_key: str) -> List[Dict]:
    """Récupère les cotes des 5 grands championnats via The Odds API (5 appels max)."""
    if not api_key:
        return []
    games: List[Dict] = []
    for sport in ODDS_API_SPORTS:
        r = safe_get(
            f"https://api.the-odds-api.com/v4/sports/{sport}/odds",
            params={
                "apiKey": api_key, "regions": "eu", "markets": "h2h",
                "oddsFormat": "decimal",
                "commenceTimeFrom": f"{date_str}T00:00:00Z",
                "commenceTimeTo":   f"{date_str}T23:59:59Z",
            },
        )
        if r and r.status_code == 200:
            try:
                data = r.json()
                if isinstance(data, list):
                    games.extend(data)
            except Exception:
                pass
    return games

def _parse_odds_game(game: Dict) -> Optional[Tuple[float, float, float]]:
    """Convertit les cotes moyennes d'un game Odds API en triplet de probabilités."""
    all_h, all_d, all_a = [], [], []
    h_name = game.get("home_team", "")
    a_name = game.get("away_team", "")
    for bm in game.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            out = {o["name"]: o["price"] for o in mkt.get("outcomes", [])}
            o1 = out.get(h_name)
            o2 = out.get(a_name)
            od = out.get("Draw")
            if o1 and o2 and od and all(1.01 < x < 50 for x in (o1, od, o2)):
                all_h.append(1/o1); all_d.append(1/od); all_a.append(1/o2)
    if all_h:
        h = sum(all_h)/len(all_h)
        d = sum(all_d)/len(all_d)
        a = sum(all_a)/len(all_a)
        return normalize_triplet(h*100, d*100, a*100)
    return None


def _enrich_df_with_external(
    df: "pd.DataFrame",
    target_date: date,
    af_key: str,
    odds_key: str,
    thresholds: Dict,
) -> "pd.DataFrame":
    """
    Post-traitement : enrichit chaque ligne avec API-Football + Odds API.
    Re-calcule weighted_triplet, decision_tree et estimate_goals si de nouvelles sources apparaissent.
    """
    if df.empty or (not af_key and not odds_key):
        return df

    date_str = target_date.isoformat()
    af_fixtures = _fetch_af_fixtures(date_str, af_key)
    odds_games  = _fetch_odds_api_games(date_str, odds_key)

    COL_MAP = {
        "site_pre_match":  "site_pre_match",
        "community_prono": "community",
        "h2h":             "h2h",
        "form":            "form",
        "odds":            "odds",
    }

    rows_out = []
    for _, row in df.iterrows():
        home = row.get("domicile", "")
        away = row.get("exterieur", "")

        # ── Reconstruire sources existantes ───────────────────────────────
        sources: Dict[str, Optional[Tuple]] = {
            k: _row_triplet(row, v) for k, v in COL_MAP.items()
        }
        added = False

        # ── API-Football ──────────────────────────────────────────────────
        if af_fixtures:
            best_score, best_fix = 0.0, None
            for fix in af_fixtures:
                t = fix.get("teams", {})
                sc = _match_score(home, away,
                                  t.get("home", {}).get("name", ""),
                                  t.get("away", {}).get("name", ""))
                if sc > best_score:
                    best_score, best_fix = sc, fix

            if best_fix and best_score >= 0.60:
                fid = best_fix.get("fixture", {}).get("id")
                if fid and af_key:
                    pred = _fetch_af_prediction(fid, af_key)
                    if pred:
                        af_probs = _parse_af_probs(pred)
                        if af_probs:
                            sources["api_football"] = af_probs
                            added = True
                        if not sources.get("form"):
                            hf, af_ = _parse_af_form(pred)
                            if hf or af_:
                                sources["form"] = form_to_triplet(hf, af_)
                                added = True
                        if not sources.get("h2h"):
                            h2h_t = _parse_af_h2h(pred)
                            if h2h_t:
                                sources["h2h"] = h2h_t
                                added = True

        # ── The Odds API ──────────────────────────────────────────────────
        if odds_games:
            best_score, best_game = 0.0, None
            for g in odds_games:
                sc = _match_score(home, away,
                                  g.get("home_team", ""), g.get("away_team", ""))
                if sc > best_score:
                    best_score, best_game = sc, g

            if best_game and best_score >= 0.55:
                og_probs = _parse_odds_game(best_game)
                if og_probs:
                    # Remplace les cotes FootMercato (moins fiables) ou en complément
                    if sources.get("odds") is None:
                        sources["odds"] = og_probs
                    else:
                        sources["odds_ext"] = og_probs
                    added = True

        # ── Re-calcul si nouvelles sources ────────────────────────────────
        if added:
            p1, px, p2, conf, n_src = weighted_triplet(sources)
            events = implied_events(p1, px, p2)
            tree   = decision_tree(p1, px, p2, conf, n_src, home, away, thresholds)
            goals  = estimate_goals(p1, px, p2)

            row = row.copy()
            row["proba_1"]   = p1
            row["proba_X"]   = px
            row["proba_2"]   = p2
            row["confiance"] = conf
            row["n_sources"] = n_src
            for k, v in {**events, **tree, **goals}.items():
                row[k] = v
            if "api_football" in sources:
                t = sources["api_football"]
                row["af_1"] = round(t[0], 2)
                row["af_X"] = round(t[1], 2)
                row["af_2"] = round(t[2], 2)

        rows_out.append(row)

    result = pd.DataFrame(rows_out)
    # Recalcule proba_plus_haute et sources_ok après enrichissement
    if not result.empty:
        result["proba_plus_haute"] = result[["proba_1", "proba_X", "proba_2"]].max(axis=1, skipna=True)
        src_cols = ["site_pre_match_1", "community_1", "h2h_1", "form_1", "odds_1", "af_1"]
        result["sources_ok"] = result[[c for c in src_cols if c in result.columns]].notna().sum(axis=1)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# MULTIPROCESSING PLAYWRIGHT — fonctions top-level (picklables)
# ══════════════════════════════════════════════════════════════════════════════

def _subprocess_playwright_fetch(url: str) -> Tuple[str, List[str]]:
    """
    Fetch avec Playwright dans un process séparé.
    Aucun appel Streamlit. Retourne (html, liste_de_réponses_json_xhr).
    Fallback silencieux sur requests si Playwright indisponible.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        try:
            r = requests.get(url, headers=HEADERS_BROWSER, timeout=REQUEST_TIMEOUT)
            return (r.text if r else ""), []
        except Exception:
            return "", []

    xhr_store: List[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=HEADERS_BROWSER["User-Agent"],
                locale="fr-FR",
                extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"},
            )
            page = ctx.new_page()

            def _on_response(response):
                if "json" in response.headers.get("content-type", "") and response.status == 200:
                    try:
                        body = response.text()
                        if body and len(body) > 30:
                            xhr_store.append(body)
                    except Exception:
                        pass

            page.on("response", _on_response)
            try:
                page.goto(url, wait_until="networkidle", timeout=35_000)
            except PWTimeout:
                pass
            page.wait_for_timeout(1500)
            html = page.content()
            browser.close()
        return html, xhr_store
    except Exception:
        try:
            r = requests.get(url, headers=HEADERS_BROWSER, timeout=REQUEST_TIMEOUT)
            return (r.text if r else ""), []
        except Exception:
            return "", []


def _mp_process_one_match(args: Tuple) -> Dict:
    """
    Fonction top-level exécutée dans un process enfant (ProcessPoolExecutor).
    Une seule requête Playwright par match : fetch + enrichissement identité + analyse probabilités.
    """
    match_dict, thresholds = args
    url = match_dict["match_url"]

    html, xhr_list = _subprocess_playwright_fetch(url)
    if not html:
        return {
            "competition": match_dict["competition"],
            "domicile":    match_dict["home_team"],
            "exterieur":   match_dict["away_team"],
            "heure":       match_dict["kickoff"],
            "url_match":   url,
            **EMPTY_ANALYSIS,
        }

    soup = BeautifulSoup(html, "html.parser")
    text = normalize(soup.get_text(" ", strip=True))

    # ── Identité (comp, home, away) ───────────────────────────────────────
    comp = match_dict["competition"]
    home = match_dict["home_team"]
    away = match_dict["away_team"]

    for el in [soup.find("meta", property="og:title"), soup.title]:
        val = normalize(
            el.get("content", "") if el and el.name == "meta"
            else (el.get_text() if el else "")
        )
        m_re = re.search(r"(.+?)\s+(?:vs\.?|contre|-)\s+(.+?)(?:\s+[-|]|$)", val, re.I)
        if m_re:
            home = home or normalize(m_re.group(1))
            away = away or normalize(m_re.group(2))
            break

    # ── Probabilités — __NEXT_DATA__ puis XHR interceptés ────────────────
    json_sources: Dict[str, Optional[Tuple]] = {}

    script = soup.find("script", id="__NEXT_DATA__")
    if script and script.string:
        try:
            json_sources = _extract_probabilities_from_json(json.loads(script.string))
        except Exception:
            pass

    for xhr_raw in xhr_list:
        try:
            probs = _extract_probabilities_from_json(json.loads(xhr_raw))
            for k, v in probs.items():
                if v is not None and k not in json_sources:
                    json_sources[k] = v
        except Exception:
            pass

    # ── Parsing HTML classique (complément) ──────────────────────────────
    pre_match  = json_sources.get("site_pre_match") or parse_pre_match(text)
    community  = json_sources.get("community_prono") or parse_community(text)
    h2h        = json_sources.get("h2h")             or parse_h2h(text)
    odds_raw   = json_sources.get("odds_raw")        or parse_odds(text)
    odds_probs = odds_to_prob(odds_raw) if odds_raw else None

    home_ser, away_ser = parse_form(text)
    form_tri = form_to_triplet(home_ser, away_ser) if (home_ser or away_ser) else None

    p1, px, p2, conf, n_src = weighted_triplet({
        "site_pre_match":  pre_match,
        "odds":            odds_probs,
        "community_prono": community,
        "form":            form_tri,
        "h2h":             h2h,
    })
    events = implied_events(p1, px, p2)
    tree   = decision_tree(p1, px, p2, conf, n_src, home, away, thresholds)
    goals  = estimate_goals(p1, px, p2)

    def _r(t, i): return round(t[i], 2) if t else None

    return {
        "competition": comp,
        "domicile":    home,
        "exterieur":   away,
        "heure":       match_dict["kickoff"],
        "url_match":   url,
        "site_pre_match_1": _r(pre_match, 0), "site_pre_match_X": _r(pre_match, 1), "site_pre_match_2": _r(pre_match, 2),
        "community_1": _r(community, 0), "community_X": _r(community, 1), "community_2": _r(community, 2),
        "h2h_1": _r(h2h, 0), "h2h_X": _r(h2h, 1), "h2h_2": _r(h2h, 2),
        "form_1": _r(form_tri, 0), "form_X": _r(form_tri, 1), "form_2": _r(form_tri, 2),
        "odds_1": _r(odds_probs, 0), "odds_X": _r(odds_probs, 1), "odds_2": _r(odds_probs, 2),
        "serie_dom": "".join(home_ser) or None,
        "serie_ext": "".join(away_ser) or None,
        "proba_1": p1, "proba_X": px, "proba_2": p2,
        "confiance": conf, "n_sources": n_src,
        **events, **tree, **goals,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────
# Fonctions pures (cachables) — AUCUN appel st.* à l'intérieur
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def _cached_fetch_matches(target_date_iso: str, use_playwright: bool = False, skip_enrich: bool = False) -> Tuple[List[Dict], Dict]:
    """
    Couche 1 + 2 : récupère (et éventuellement enrichit) les matchs.
    skip_enrich=True : retourne la liste brute sans visiter les pages détail
    (utilisé en mode Playwright parallèle où l'enrichissement se fait dans le process enfant).
    Aucun appel st.* ici.
    """
    target_date = date.fromisoformat(target_date_iso)
    debug: Dict = {"playwright": use_playwright, "skip_enrich": skip_enrich}
    matches: List[MatchRow] = []

    # Couche 1 : API JSON
    api_data = try_api_calendar(target_date)
    if api_data:
        for raw in api_data:
            m = normalize_api_match(raw)
            if m:
                matches.append(m)
        debug["source"] = "API JSON"
        debug["raw_api_count"] = len(api_data)

    # Couche 2 : HTML scraping (toujours en requests — rapide)
    if not matches:
        live_url = build_live_url(target_date)
        debug["source"]   = "requests scraping (liste)"
        debug["live_url"] = live_url
        html = fetch_page(live_url, use_playwright=False)   # requests pour la liste
        if not html:
            return [], {**debug, "error": "Page inaccessible"}
        matches = extract_matches_html(html, target_date)
        debug["raw_html_count"] = len(matches)
        if matches and not skip_enrich:
            matches = enrich_matches_parallel(matches, use_playwright=use_playwright)

    debug["matches_after_enrichment"] = len(matches)

    return [
        {
            "competition": m.competition,
            "home_team":   m.home_team,
            "away_team":   m.away_team,
            "kickoff":     m.kickoff,
            "match_url":   m.match_url,
            "match_id":    m.match_id,
        }
        for m in matches
    ], debug


@st.cache_data(ttl=600, show_spinner=False)
def _cached_analyse_all(match_dicts: str, thresholds_hash: str, use_playwright: bool = False) -> List[Dict]:
    """
    Analyse tous les matchs. match_dicts est un JSON string (hashable).
    Aucun appel st.* ici.
    """
    matches = json.loads(match_dicts)
    output  = []
    for m in matches:
        analysis = analyse_match(m["match_url"], m["home_team"], m["away_team"], thresholds_hash, use_playwright=use_playwright)
        item = {
            "competition": m["competition"],
            "domicile":    m["home_team"],
            "exterieur":   m["away_team"],
            "heure":       m["kickoff"],
            "url_match":   m["match_url"],
        }
        item.update(analysis)
        output.append(item)
    return output


def _finalize_dataframe(rows: List[Dict]) -> pd.DataFrame:
    """Construit et enrichit le DataFrame final. Pure Python, pas de cache."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    for col in ["proba_1", "proba_X", "proba_2"]:
        if col not in df.columns:
            df[col] = pd.NA

    df["proba_plus_haute"] = df[["proba_1", "proba_X", "proba_2"]].max(axis=1, skipna=True)

    def _best(row):
        vals = {"1": row.get("proba_1"), "N": row.get("proba_X"), "2": row.get("proba_2")}
        valid = {k: v for k, v in vals.items() if v is not None and not pd.isna(v)}
        return max(valid, key=valid.get) if valid else None

    df["issue_modele"] = df.apply(_best, axis=1)

    src_cols = ["site_pre_match_1", "community_1", "h2h_1", "form_1", "odds_1"]
    df["sources_ok"] = df[[c for c in src_cols if c in df.columns]].notna().sum(axis=1)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrateur appelé depuis l'UI (avec st.* autorisé)
# ─────────────────────────────────────────────────────────────────────────────
def build_dataframe(
    target_date_iso: str,
    thresholds_hash: str,
    use_playwright: bool = False,
    thresholds: Optional[Dict] = None,
    af_key: str = "",
    odds_key: str = "",
) -> Tuple[pd.DataFrame, Dict]:
    """
    Orchestre le pipeline en affichant la progression.
    Appelé directement depuis l'UI — jamais mis en cache lui-même.

    Mode requests  : liste → enrich (10 threads) → analyse (10 threads) — ~30-60 s
    Mode Playwright: liste (requests) → fetch+enrich+analyse x4 process — ~3-4 min
    """
    T = thresholds or DEFAULT_THRESHOLDS
    mode_label = f"Playwright x{PLAYWRIGHT_WORKERS} 🎭" if use_playwright else "requests ⚡"

    with st.status(f"🔍 Récupération des matchs ({mode_label})…", expanded=True) as status:

        # ── Étape 1 : liste des matchs (toujours en requests, ~10 s) ─────────
        st.write("⚡ Récupération de la liste des matchs (requests)…")
        match_dicts, debug = _cached_fetch_matches(
            target_date_iso,
            use_playwright=False,
            skip_enrich=use_playwright,   # skip si Playwright gère tout
        )
        n = len(match_dicts)
        st.write(f"✅ {n} match(s) trouvé(s).")
        if n == 0:
            status.update(label="Aucun match trouvé.", state="error")
            return pd.DataFrame(), debug

        # ── Étape 2a : mode Playwright parallèle ─────────────────────────────
        if use_playwright and PLAYWRIGHT_OK:
            st.write(
                f"🎭 Lancement de {PLAYWRIGHT_WORKERS} navigateurs Chromium en parallèle…  "
                f"(~{max(1, n // PLAYWRIGHT_WORKERS * 4)} s estimés)"
            )
            progress_bar = st.progress(0, text="0 / " + str(n))
            args = [(m, T) for m in match_dicts]
            rows: List[Dict] = []
            completed = 0

            with ThreadPoolExecutor(max_workers=PLAYWRIGHT_WORKERS) as pool:
                futures = {pool.submit(_mp_process_one_match, a): a for a in args}
                for future in as_completed(futures):
                    try:
                        rows.append(future.result())
                    except Exception:
                        orig, _ = futures[future]   # args = (match_dict, T)
                        rows.append({
                            "competition": orig["competition"],
                            "domicile":    orig["home_team"],
                            "exterieur":   orig["away_team"],
                            "heure":       orig["kickoff"],
                            "url_match":   orig["match_url"],
                            **EMPTY_ANALYSIS,
                        })
                    completed += 1
                    progress_bar.progress(completed / n, text=f"{completed} / {n}")

            debug["source"] = f"Playwright x{PLAYWRIGHT_WORKERS} (multiprocessing)"

        # ── Étape 2b : mode requests séquentiel (avec cache Streamlit) ────────
        else:
            if not use_playwright:
                # enrichissement non fait dans _cached_fetch_matches → faire maintenant
                pass   # déjà fait (skip_enrich=False en mode requests)
            st.write("Analyse des probabilités (requests)…")
            rows = _cached_analyse_all(json.dumps(match_dicts), thresholds_hash)

        status.update(label=f"✅ {n} match(s) analysé(s) via {mode_label}.", state="complete")

    df = _finalize_dataframe(rows)

    # ── Enrichissement sources externes (API-Football + Odds API) ─────────
    if af_key or odds_key:
        with st.spinner("🌐 Enrichissement via sources externes (API-Football / Odds API)…"):
            df = _enrich_df_with_external(df, date.fromisoformat(target_date_iso), af_key, odds_key, T)
            debug["external_enrichment"] = {
                "api_football": bool(af_key),
                "odds_api":     bool(odds_key),
            }

    if "sources_ok" in df.columns:
        debug["with_at_least_1_source"] = int((df["sources_ok"] >= 1).sum())
        debug["with_0_sources"]         = int((df["sources_ok"] == 0).sum())

    return df, debug


# ══════════════════════════════════════════════════════════════════════════════
# INTERFACE STREAMLIT
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="⚽ Pronostics FootMercato", layout="wide")
require_auth()

st.markdown("""
<style>
[data-testid="stSidebar"] { min-width: 280px; }
.metric-card { background:#1e1e2e; border-radius:8px; padding:12px 16px; margin:4px 0; }
</style>
""", unsafe_allow_html=True)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Paramètres")

    # Sélection de date
    st.subheader("📅 Date")
    today = date.today()
    date_option = st.radio(
        "Raccourcis",
        ["Aujourd'hui", "Demain", "J+2", "Choisir une date"],
        horizontal=False,
    )
    if date_option == "Aujourd'hui":
        target_date = today
    elif date_option == "Demain":
        target_date = today + timedelta(days=1)
    elif date_option == "J+2":
        target_date = today + timedelta(days=2)
    else:
        target_date = st.date_input(
            "Date",
            value=today,
            min_value=today - timedelta(days=7),
            max_value=today + timedelta(days=7),
        )

    st.info(f"📅 **{target_date.strftime('%A %d %B %Y')}**")

    st.divider()

    # Seuils ajustables
    st.subheader("🎯 Seuils arbre de décision")
    T = DEFAULT_THRESHOLDS.copy()
    T["min_confidence"]        = st.slider("Confiance min (%)",        0,  80, int(T["min_confidence"]),    step=5)
    T["min_proba_bet"]         = st.slider("Proba min pour parier (%)", 45, 75, int(T["min_proba_bet"]),     step=1)
    T["high_confidence_proba"] = st.slider("Seuil 🟢 Sûr (%)",         50, 80, int(T["high_confidence_proba"]), step=1)
    T["premium_proba"]         = st.slider("Seuil ⭐ Premium (%)",      55, 85, int(T["premium_proba"]),     step=1)
    T["dc_min_proba"]          = st.slider("DC min pour proposer (%)",  50, 75, int(T["dc_min_proba"]),      step=1)
    T["min_sources"]           = st.slider("Sources min",                1,  5,  int(T["min_sources"]))

    thresholds_hash = hashlib.md5(json.dumps(T, sort_keys=True).encode()).hexdigest()[:8]

    st.divider()
    st.subheader("📊 Filtres affichage")
    filter_niveau = st.multiselect(
        "Niveaux à afficher",
        ["⭐ Premium", "🟢 Sûr", "🟡 Prudent", "🔴 SKIP"],
        default=["⭐ Premium", "🟢 Sûr", "🟡 Prudent"],
    )
    min_sources_display = st.slider("Sources min (affichage)", 0, 5, 0)

    st.divider()
    st.subheader("🎭 Mode de fetch")

    if PLAYWRIGHT_OK:
        use_playwright = st.toggle(
            "Utiliser Playwright (JS rendu)",
            value=False,
            help=(
                "Active Chromium headless pour charger les pages avec JavaScript. "
                "Récupère les données dynamiques (probabilités, cotes…) chargées en XHR. "
                "⚠️ Plus lent : ~3–5 s par page au lieu de ~0,5 s."
            ),
        )
        if use_playwright:
            st.success("🎭 Playwright actif — couverture maximale")
        else:
            st.info("⚡ Mode rapide (requests) — JS non exécuté")
    else:
        use_playwright = False
        st.warning(
            "Playwright non installé.\n\n"
            "```bash\npip install playwright\nplaywright install chromium\n```"
        )

    st.divider()
    st.subheader("🌐 Sources externes (optionnel)")
    st.caption("Clés API pour enrichir les probabilités. Laisse vide pour ignorer.")
    af_key   = st.text_input("Clé API-Football (RapidAPI)", type="password",
                              value=st.secrets.get("api_football_key", ""),
                              help="Gratuit : 100 req/jour — rapidapi.com/api-sports/api/api-football")
    odds_key = st.text_input("Clé The Odds API", type="password",
                              value=st.secrets.get("odds_api_key", ""),
                              help="Gratuit : 500 req/mois — the-odds-api.com")
    if af_key:
        st.success("✅ API-Football configurée")
    if odds_key:
        st.success("✅ The Odds API configurée")

    st.divider()
    st.subheader("🏆 Filtre championnats")
    only_major = st.toggle(
        "5 grands championnats uniquement",
        value=False,
        help="Premier League · La Liga · Bundesliga · Serie A · Ligue 1",
    )

    st.divider()
    if st.button("🗑️ Vider le cache", use_container_width=True):
        st.cache_data.clear()
        st.success("Cache vidé !")

# ── HEADER ────────────────────────────────────────────────────────────────────
st.title("⚽ Pronostics FootMercato")
st.caption(
    "Sources : probabilités site · cotes bookmakers · communauté · forme · H2H. "
    "Arbre de décision avec seuils configurables."
)

# Légende
with st.expander("📖 Comment ça marche ?", expanded=False):
    st.markdown(f"""
### 🔍 Sources de données

**1. FootMercato (source principale)**
L'app scrape footmercato.net pour chaque match : probabilités 1X2, cotes, pronos communauté, forme, H2H.
FootMercato utilise React/JS — deux modes disponibles :
- **⚡ Mode rapide (requests)** : HTML statique, rapide mais couverture partielle
- **🎭 Mode Playwright** : navigateur Chromium headless, charge le JS → couverture maximale (~4 min)

**2. API-Football** *(RapidAPI — 100 req/jour)*
Probabilités officielles, forme récente, historique H2H issus de la base de données API-Football.

**3. The Odds API** *(500 req/mois)*
Cotes de vrais bookmakers → probabilités implicites du marché.

---

### ⚖️ Fusion des sources

| Source | Poids |
|--------|-------|
| Probabilités FootMercato | 35 % |
| Cotes FootMercato | 22 % |
| API-Football | 12 % |
| The Odds API | 8 % |
| Communauté | 9 % |
| Forme | 9 % |
| H2H | 5 % |

---

### 🎯 Niveaux de décision

| Niveau | Conditions | Action |
|--------|-----------|--------|
| ⭐ **Premium** | Proba ≥ {T['premium_proba']} %, écart ≥ {T['premium_gap']:.0f} pts, confiance ≥ 60 % | ✅ Mise pleine |
| 🟢 **Sûr** | Proba ≥ {T['high_confidence_proba']} % ou (écart ≥ 10 pts et confiance ≥ 50 %) | ✅ Mise normale |
| 🟡 **Prudent** | Proba ≥ {T['min_proba_bet']} % — DC ou DNB possible | ⚠️ Mise réduite |
| 🔴 **SKIP** | Proba < {T['min_proba_bet']} % ou confiance < {T['min_confidence']} % | ❌ Ne pas parier |

La **confiance** mesure l'écart entre la meilleure probabilité et les autres issues — plus l'écart est grand, plus le signal est fiable.

---

### ⚽ Paris sur les buts

Un **modèle Poisson** estime le nombre de buts attendus à partir des probas 1X2, et calcule la probabilité de chaque marché : Over/Under 0.5 à 4.5, BTTS Oui/Non.
Seuls les marchés ≥ 65 % sont affichés.
""")

# ── LANCEMENT ─────────────────────────────────────────────────────────────────
run = st.button(
    f"🚀 Analyser les matchs du {target_date.strftime('%d/%m/%Y')}",
    type="primary",
    use_container_width=True,
)

if not run:
    st.stop()

df, debug_info = build_dataframe(
    target_date.isoformat(),
    thresholds_hash,
    use_playwright=use_playwright,
    thresholds=T,
    af_key=af_key,
    odds_key=odds_key,
)

with st.expander("🔧 Debug", expanded=False):
    st.json(debug_info)

if df.empty:
    st.error("Aucun match trouvé. Vérifiez la connexion ou changez de date.")
    st.stop()

# ── KPIs ──────────────────────────────────────────────────────────────────────
total     = len(df)
with_data = int((df.get("sources_ok", pd.Series([0]*total)) >= 1).sum()) if "sources_ok" in df.columns else 0
bets_df   = df[df["signal_type"].isin(["1","2","N","1N","X2","12","DNB_1","DNB_2"])] if "signal_type" in df.columns else pd.DataFrame()
premium_n = int((df["niveau"] == "⭐ Premium").sum()) if "niveau" in df.columns else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Matchs trouvés",      total)
k2.metric("Avec données",        with_data,  f"{int(100*with_data/max(total,1))} %")
k3.metric("Paris recommandés",   len(bets_df))
k4.metric("⭐ Premium",          premium_n)

st.divider()

# ── Filtrage ──────────────────────────────────────────────────────────────────
filtered = df.copy()
if only_major and "competition" in filtered.columns:
    def _is_major(comp):
        if not comp:
            return False
        c = comp.lower()
        return any(kw in c for kw in MAJOR_LEAGUE_KEYWORDS)
    filtered = filtered[filtered["competition"].apply(_is_major)]
if filter_niveau and "niveau" in filtered.columns:
    filtered = filtered[filtered["niveau"].isin(filter_niveau)]
if "sources_ok" in filtered.columns:
    filtered = filtered[filtered["sources_ok"] >= min_sources_display]

# Tri
sort_col = st.selectbox(
    "Trier par",
    ["confiance", "proba_plus_haute", "signal_proba", "heure", "competition"],
    index=0,
)
filtered = filtered.sort_values(sort_col, ascending=False, na_position="last")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — SÉLECTION AUTOMATIQUE (grille de décision complète)
# ══════════════════════════════════════════════════════════════════════════════
ACTIONABLE = {"✅ Mise pleine", "✅ Mise normale", "⚠️ Mise réduite", "⚠️ Mise réduite — peu de sources", "⚠️ Petite mise ou DC/DNB"}

auto_df = pd.DataFrame()
if "action" in filtered.columns:
    auto_df = filtered[filtered["action"].isin(ACTIONABLE)].copy()
    auto_df = auto_df.sort_values(
        ["action", "confiance", "signal_proba"],
        ascending=[True, False, False],
        na_position="last",
    )

ACTION_COLOR = {
    "✅ Mise pleine":                    "🟩",
    "✅ Mise normale":                   "🟩",
    "⚠️ Mise réduite":                  "🟨",
    "⚠️ Mise réduite — peu de sources": "🟨",
    "⚠️ Petite mise ou DC/DNB":         "🟧",
}

st.subheader(f"🎯 Sélection automatique — Paris à jouer ({len(auto_df)})")

if auto_df.empty:
    st.info("Aucun match retenu par la grille de décision avec les filtres actuels.")
else:
    for _, row in auto_df.iterrows():
        action = row.get("action", "")
        bullet = ACTION_COLOR.get(action, "⬜")
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([1.2, 2.8, 2, 2, 2])
            with c1:
                st.markdown(f"**{row.get('heure','?')}**")
                st.caption(row.get("competition", "")[:28])
            with c2:
                st.markdown(f"**{row.get('domicile','')}**")
                st.markdown(f"*vs* **{row.get('exterieur','')}**")
            with c3:
                st.markdown(f"{row.get('niveau','')}  \n**{row.get('signal','—')}**")
                st.caption(f"`{row.get('signal_proba',0):.1f} %` · {row.get('n_sources',0)} src")
            with c4:
                st.markdown(f"{bullet} **{action}**")
                st.caption(f"Confiance : **{row.get('confiance',0):.0f} %**")
            with c5:
                st.caption(row.get("explication", ""))

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — PARIS SUR LES BUTS
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("⚽ Meilleures opportunités sur les buts")
st.caption("Basé sur un modèle Poisson calibré sur les probabilités 1X2. Seuil d'affichage : ≥ 65 %.")

GOAL_THRESHOLD = 65.0

if "over_25" in filtered.columns:
    goals_rows = []
    for _, row in filtered.iterrows():
        domicile  = row.get("domicile", "")
        exterieur = row.get("exterieur", "")
        heure     = row.get("heure", "?")
        comp      = row.get("competition", "")
        lam       = row.get("buts_esp_total")
        label     = f"{domicile} — {exterieur}"

        candidates = [
            ("Over 0.5",  row.get("over_05")),
            ("Over 1.5",  row.get("over_15")),
            ("Over 2.5",  row.get("over_25")),
            ("Over 3.5",  row.get("over_35")),
            ("Over 4.5",  row.get("over_45")),
            ("Under 1.5", row.get("under_15")),
            ("Under 2.5", row.get("under_25")),
            ("Under 3.5", row.get("under_35")),
            ("BTTS Oui",  row.get("btts_oui")),
            ("BTTS Non",  row.get("btts_non")),
        ]
        for market, proba in candidates:
            if proba is not None and proba >= GOAL_THRESHOLD:
                goals_rows.append({
                    "Heure":    heure,
                    "Match":    label,
                    "Compétition": comp[:28],
                    "Marché":   market,
                    "Proba (%)": proba,
                    "λ total":  lam,
                    "url":      row.get("url_match", ""),
                })

    if goals_rows:
        goals_df = (
            pd.DataFrame(goals_rows)
            .sort_values("Proba (%)", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(
            goals_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "url":       st.column_config.LinkColumn("Lien"),
                "Proba (%)": st.column_config.ProgressColumn("Proba (%)", min_value=0, max_value=100, format="%.1f %%"),
                "λ total":   st.column_config.NumberColumn("Buts attendus", format="%.2f"),
            },
        )
    else:
        st.info("Aucun marché buts ≥ 65 % avec les filtres actuels.")
else:
    st.info("Les données de buts ne sont pas disponibles (analyse non effectuée).")

st.divider()

# ── Tableau complet ────────────────────────────────────────────────────────────
st.subheader(f"📊 Tableau complet ({len(filtered)} matchs)")

display_cols = [
    "heure", "competition", "domicile", "exterieur",
    "niveau", "signal", "signal_proba", "n_sources",
    "proba_1", "proba_X", "proba_2", "proba_plus_haute", "confiance",
    "DC_1N", "DC_X2", "DC_12", "DNB_1", "DNB_2",
    "serie_dom", "serie_ext",
    "odds_1", "odds_X", "odds_2",
    "url_match",
]

st.dataframe(
    filtered[[c for c in display_cols if c in filtered.columns]],
    use_container_width=True,
    hide_index=True,
    column_config={
        "url_match":      st.column_config.LinkColumn("Lien"),
        "proba_1":        st.column_config.NumberColumn("1 (%)",     format="%.1f"),
        "proba_X":        st.column_config.NumberColumn("N (%)",     format="%.1f"),
        "proba_2":        st.column_config.NumberColumn("2 (%)",     format="%.1f"),
        "proba_plus_haute": st.column_config.NumberColumn("Max (%)", format="%.1f"),
        "signal_proba":   st.column_config.NumberColumn("Proba signal", format="%.1f"),
        "confiance":      st.column_config.NumberColumn("Confiance", format="%.0f"),
        "n_sources":      st.column_config.NumberColumn("Sources",   format="%d"),
        "DC_1N":          st.column_config.NumberColumn("DC 1N",     format="%.1f"),
        "DC_X2":          st.column_config.NumberColumn("DC X2",     format="%.1f"),
        "DC_12":          st.column_config.NumberColumn("DC 12",     format="%.1f"),
        "DNB_1":          st.column_config.NumberColumn("DNB Dom",   format="%.1f"),
        "DNB_2":          st.column_config.NumberColumn("DNB Ext",   format="%.1f"),
        "odds_1":         st.column_config.NumberColumn("Odds 1→%",  format="%.1f"),
        "odds_X":         st.column_config.NumberColumn("Odds N→%",  format="%.1f"),
        "odds_2":         st.column_config.NumberColumn("Odds 2→%",  format="%.1f"),
    },
)

csv = filtered.to_csv(index=False).encode("utf-8")
st.download_button("📥 Télécharger CSV", data=csv,
                   file_name=f"pronostics_{target_date.isoformat()}.csv", mime="text/csv")

# ── Diagnostic données manquantes ─────────────────────────────────────────────
if "sources_ok" in df.columns:
    n_empty = int((df["sources_ok"] == 0).sum())
    if n_empty > 0:
        with st.expander(f"⚠️ {n_empty} match(s) sans données — Pourquoi ?", expanded=False):
            st.markdown("""
### Cause principale : rendu JavaScript

FootMercato injecte ses probabilités **après** le chargement de la page via des
appels XHR/Fetch (React/Next.js). `requests` + BeautifulSoup ne voit que le HTML initial,
**sans les données dynamiques**.

### Solutions

**Option A — Playwright (recommandé, 100 % de couverture)**
```bash
pip install playwright
playwright install chromium
```
Remplacez `safe_get(url)` par :
```python
from playwright.sync_api import sync_playwright

def fetch_with_js(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        content = page.content()
        browser.close()
    return content
```

**Option B — Intercepter les appels XHR**  
Ouvrez DevTools → onglet **Réseau** → filtre **Fetch/XHR** → rechargez la page.  
Repérez les appels vers `/api/...` et adaptez `try_api_calendar()` dans ce script.

**Option C — Selenium**
```bash
pip install selenium webdriver-manager
```
""")
            st.dataframe(
                df[df["sources_ok"] == 0][["competition","domicile","exterieur","heure","url_match"]],
                use_container_width=True, hide_index=True,
                column_config={"url_match": st.column_config.LinkColumn("Lien")},
            )