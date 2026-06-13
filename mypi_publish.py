"""
MyPI — Publication automatique des menus
Lit la configuration dans mypi_config.json (même dossier que ce script).

Prérequis :
    pip install selenium
    ChromeDriver installé et dans le PATH (ou utiliser webdriver-manager)

Usage :
    python mypi_publish.py
"""

import io
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# ── Encodage console Windows ──────────────────────────────────────────────────

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ── Constantes ────────────────────────────────────────────────────────────────

CONFIG_PATH   = Path(__file__).parent / "mypi_config.json"
LOG_PATH      = Path(__file__).parent / "mypi_publish.log"
URL_MENUS     = "https://configurateur.mypi.net/menus"
WAIT_DEFAULT  = 15   # secondes max pour trouver un élément
WAIT_PUBLISH  = 8    # secondes après le clic Publier


# ── Logging (console + fichier) ───────────────────────────────────────────────

_logger = logging.getLogger("mypi")
_logger.setLevel(logging.DEBUG)

_fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")

_ch = logging.StreamHandler(sys.stdout)
_ch.setFormatter(_fmt)
_logger.addHandler(_ch)

_fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
_fh.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
_logger.addHandler(_fh)


def log(msg: str):
    _logger.info(msg)


def wait_click(driver, by, value, timeout=WAIT_DEFAULT):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"[ERREUR] Fichier introuvable : {CONFIG_PATH}")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8").strip())
    if "exemple.com" in config.get("email", ""):
        sys.exit("[ERREUR] Identifiants par défaut détectés — mettez à jour mypi_config.json.")
    return config


# ── Étapes ────────────────────────────────────────────────────────────────────

def login(driver, email: str, password: str):
    """
    Connexion sur auth.mypi.net (Auth0).
    Le formulaire affiche email + mot de passe sur la même page.
    Le bouton submit visible est le seul non-caché (aria-hidden != true).
    """
    log("Connexion…")
    driver.get(URL_MENUS)

    # Attendre le champ email visible
    champ_email = WebDriverWait(driver, 20).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='username']"))
    )
    champ_email.clear()
    champ_email.send_keys(email)

    champ_mdp = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='password'], input[type='password']"))
    )
    champ_mdp.clear()
    champ_mdp.send_keys(password)

    # Cliquer sur le bouton Continuer VISIBLE (exclure les boutons cachés aria-hidden)
    bouton = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((
            By.CSS_SELECTOR,
            "button[type='submit']:not([aria-hidden='true']):not(.ulp-hidden-form-submit-button)"
        ))
    )
    driver.execute_script("arguments[0].click();", bouton)

    # S'assurer d'être sur le bon onglet (Auth0 peut en ouvrir un nouveau)
    time.sleep(2)
    driver.switch_to.window(driver.window_handles[-1])
    # Attendre la redirection vers le configurateur
    WebDriverWait(driver, 20).until(EC.url_contains("configurateur.mypi.net/menus"))
    log("Connecté ✓")


def ouvrir_selecteur(driver):
    """
    Ouvre le modal 'Sélectionnez un site'.
    Le sélecteur est le web component <ath-main-site-selector> dans le header.
    On clique l'élément interne (shadow DOM) ou l'hôte selon ce qui répond.
    """
    fermer_panneau_si_ouvert(driver)

    # DEBUG : lister les éléments du header pour diagnostic
    info = driver.execute_script("""
        const header = document.querySelector('header, nav, [class*="header"], [class*="toolbar"]');
        if (!header) return 'HEADER INTROUVABLE';
        const btns = Array.from(header.querySelectorAll('button, [role="button"], [class*="selector"], [class*="site"]'));
        return btns.map((b, i) => i + ': tag=' + b.tagName
            + ' text="' + (b.innerText || '').trim().substring(0, 40) + '"'
            + ' aria="' + (b.getAttribute('aria-label') || '') + '"'
            + ' class="' + b.className.substring(0, 40) + '"'
        ).join(' || ');
    """)
    log(f"DEBUG sélecteur — boutons header : {info}")

    cliqué = driver.execute_script("""
        // Essai 1 : web component ath-main-site-selector → bouton dans son shadow DOM
        const comp = document.querySelector('ath-main-site-selector');
        if (comp) {
            const inner = comp.shadowRoot
                ? comp.shadowRoot.querySelector('button, [role="button"], [class*="trigger"], [class*="select"]')
                : null;
            if (inner) { inner.click(); return 'shadow-inner'; }
            comp.click(); return 'comp-host';
        }
        // Essai 2 : sélecteur générique dans le header
        const header = document.querySelector('header, nav, [class*="header"], [class*="toolbar"]');
        if (!header) return 'no-header';
        const btns = Array.from(header.querySelectorAll('button, [role="button"], [class*="selector"], [class*="site"]'));
        const explicit = btns.find(b => /selector|site/i.test(b.className));
        if (explicit) { explicit.click(); return 'explicit-class'; }
        const byLabel = btns.find(b => /site|établissement|etab/i.test(b.getAttribute('aria-label') || ''));
        if (byLabel) { byLabel.click(); return 'by-label'; }
        const fallback = btns.find(b => b.innerText && b.innerText.trim().length > 2) || btns[0];
        if (fallback) { fallback.click(); return 'fallback'; }
        return 'nothing';
    """)
    log(f"DEBUG sélecteur — stratégie utilisée : {cliqué}")
    time.sleep(1.5)


def clique_js(driver, js_find_expr: str):
    """Trouve un élément via JS et le clique."""
    el = driver.execute_script(f"return (function(){{ {js_find_expr} }})();")
    if not el:
        raise NoSuchElementException(f"Élément JS introuvable.")
    driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", el)
    return el


def fermer_panneau_si_ouvert(driver):
    """
    Vérifie si le panneau 'Gestion de la carte web' est ouvert et le ferme.
    XPath exact : /html/body/div[1]/div/header/div[2]/ul/li[5]/button
    """
    try:
        btn = driver.find_element(By.XPATH,
            "//button[contains(@aria-label,'carte web') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'carte web')]"
        )
        if btn.is_displayed():
            log("Panneau 'Gestion de la carte web' ouvert — fermeture…")
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1.5)
            log("Panneau fermé ✓")
    except NoSuchElementException:
        pass  # Panneau non ouvert


def selectionner_etablissement(driver, nom: str):
    """
    Ouvre le modal et sélectionne l'établissement par son nom exact.
    Le modal contient des radio buttons avec labels (texte = nom de l'établissement).
    """
    log(f"Sélection : {nom}")

    log("DEBUG 1 : fermer_panneau_si_ouvert")
    fermer_panneau_si_ouvert(driver)

    log("DEBUG 2 : ouvrir_selecteur")
    ouvrir_selecteur(driver)

    log("DEBUG 3 : attente modal 'Sélectionnez'")
    # Attendre que le modal soit visible (light DOM ou shadow DOM)
    def modal_visible(d):
        # Cherche dans le light DOM
        try:
            el = d.find_element(By.XPATH, "//*[contains(text(),'Sélectionnez')]")
            if el.is_displayed():
                return True
        except NoSuchElementException:
            pass
        # Cherche dans les shadow DOM (web components)
        return d.execute_script("""
            function searchShadow(root) {
                for (const el of root.querySelectorAll('*')) {
                    if (el.shadowRoot) {
                        const found = el.shadowRoot.querySelector('*');
                        if (found) {
                            const all = el.shadowRoot.querySelectorAll('*');
                            for (const n of all) {
                                if (n.textContent && n.textContent.includes('Sélectionnez') && n.offsetParent !== null)
                                    return true;
                            }
                        }
                        if (searchShadow(el.shadowRoot)) return true;
                    }
                }
                return false;
            }
            return searchShadow(document.body);
        """)
    WebDriverWait(driver, 10).until(modal_visible)

    log("DEBUG 4 : recherche radio button")
    # Log des options disponibles dans le modal pour faciliter le débogage
    options_dispo = driver.execute_script("""
        return Array.from(document.querySelectorAll(
            'input[type="radio"], [role="radio"], label, [class*="option"], [class*="item"]'
        )).map(el => (el.innerText || el.getAttribute('aria-label') || '').trim())
          .filter(t => t.length > 0).slice(0, 20).join(' | ');
    """)
    log(f"DEBUG 4b — options modal : {options_dispo}")

    # Trouver le radio correspondant au nom (exact ou contenu)
    try:
        radio = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                f"//input[@type='radio' and @aria-label='{nom}']"
                f" | //label[normalize-space(text())='{nom}']"
                f" | //span[normalize-space(text())='{nom}']/ancestor::label[1]"
            ))
        )
    except TimeoutException:
        # Repli : recherche par contenu partiel (robuste aux variations typographiques)
        log(f"⚠️  Nom exact '{nom}' non trouvé — tentative par contenu partiel…")
        radio = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.XPATH,
                f"//label[contains(normalize-space(.), '{nom}')]"
                f" | //span[contains(normalize-space(.), '{nom}')]/ancestor::label[1]"
                f" | //input[@type='radio' and contains(@aria-label, '{nom}')]"
            ))
        )

    log("DEBUG 5 : clic radio")
    driver.execute_script("arguments[0].click();", radio)

    # Attendre le rechargement de la carte web
    time.sleep(3)
    log(f"'{nom}' chargé ✓")


def ouvrir_panneau_publication(driver):
    """
    Clique sur l'icône fusée (🚀) en haut à droite pour ouvrir
    le panneau 'Gestion de la carte web'.
    Sur le site réel, l'aria-label est 'Publier sur les plateformes'.
    """
    log("Ouverture du panneau de publication…")

    # Essai 1 : aria-label direct
    for selector in [
        "button[aria-label='Publier sur les plateformes']",
        "button[title='Publier sur les plateformes']",
        "[aria-label*='Publier']",
    ]:
        try:
            btn = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            btn.click()
            time.sleep(2)
            log("Panneau ouvert ✓")
            return
        except TimeoutException:
            continue

    # Essai 2 : bouton dont le contenu texte est le nom de l'icône "rocket"
    try:
        btn = WebDriverWait(driver, 4).until(
            EC.element_to_be_clickable((By.XPATH,
                "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'rocket')]"
            ))
        )
        btn.click()
        time.sleep(2)
        log("Panneau ouvert via icône rocket ✓")
        return
    except TimeoutException:
        pass

    # Essai 3 : recherche récursive dans les shadow DOM via JS (aria-label ou texte rocket/publi)
    btn = driver.execute_script("""
        function find(root) {
            if (!root) return null;
            for (const el of root.querySelectorAll('button, [role="button"]')) {
                const label = (el.getAttribute('aria-label') || el.getAttribute('title') || '').toLowerCase();
                const text  = (el.innerText || el.textContent || '').toLowerCase();
                if (label.includes('publi') || text.includes('rocket')) return el;
                if (el.shadowRoot) { const r = find(el.shadowRoot); if (r) return r; }
            }
            return null;
        }
        return find(document.body);
    """)
    if btn:
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(2)
        log("Panneau ouvert via shadow DOM ✓")
        return

    raise NoSuchElementException(
        "Icône 'Publier sur les plateformes' introuvable. "
        "L'interface MyPI a peut-être changé."
    )


def publier(driver) -> str:
    """
    Clique sur le bouton bleu 'Publier' dans le panneau latéral.
    Retourne la date/heure de dernière publication lue dans le panneau.
    """
    log("Clic sur Publier…")

    btn_publier = wait_click(driver, By.XPATH,
        "//button[contains(.,'Publier') and not(@disabled)]"
    )
    btn_publier.click()

    # Attendre la fin du spinner (le bouton redevient cliquable)
    log("Publication en cours…")
    time.sleep(WAIT_PUBLISH)

    # Lire la date de dernière publication pour confirmation
    try:
        date_el = driver.find_element(By.XPATH,
            "//*[contains(text(),'Dernière publication')]/following-sibling::* | "
            "//*[contains(text(),'Dernière publication')]/following::*[1]"
        )
        date_pub = date_el.text.strip()
    except NoSuchElementException:
        date_pub = "date inconnue"

    log(f"Publié ✓ (dernière publication : {date_pub})")
    return date_pub


def fermer_panneau(driver):
    """Ferme le panneau latéral via la croix × (JS click pour éviter l'interception par le drawer)."""
    try:
        btn_close = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH,
                "//button[@aria-label='Fermer' or @aria-label='Close' "
                "or normalize-space(text())='×' or normalize-space(text())='✕' "
                "or normalize-space(text())='x']"
            ))
        )
        driver.execute_script("arguments[0].click();", btn_close)
        time.sleep(1)
    except TimeoutException:
        log("⚠️  Panneau non fermé automatiquement.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    _logger.info("=" * 60)
    _logger.info(f"  DÉMARRAGE  —  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    _logger.info("=" * 60)

    config = load_config()

    options = webdriver.ChromeOptions()
    # options.add_argument("--headless=new")  # décommenter pour lancer sans fenêtre
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-background-timer-throttling")

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(0)  # attentes gérées manuellement

    resultats = {}

    try:
        login(driver, config["email"], config["mot_de_passe"])
        fermer_panneau_si_ouvert(driver)

        for etab in config["etablissements"]:
            nom = etab["nom"]
            log(f"\n{'─' * 50}")
            try:
                selectionner_etablissement(driver, nom)
                ouvrir_panneau_publication(driver)
                date_pub = publier(driver)
                resultats[nom] = {"ok": True, "date": date_pub}
                fermer_panneau(driver)
            except Exception as e:
                log(f"❌ Erreur pour '{nom}' : {e}")
                resultats[nom] = {"ok": False, "erreur": str(e)}
                try:
                    fermer_panneau(driver)
                except Exception:
                    pass

    except Exception as e:
        log(f"❌ Erreur générale : {e}")

    finally:
        driver.quit()

    # Rapport final
    lignes = [
        "",
        "═" * 50,
        f"  RAPPORT  —  {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "═" * 50,
    ]
    for nom, res in resultats.items():
        if res["ok"]:
            lignes.append(f"  ✅  {nom}  (publié le {res['date']})")
        else:
            lignes.append(f"  ❌  {nom}  —  {res['erreur']}")
    lignes.append("═" * 50)

    for ligne in lignes:
        _logger.info(ligne)


if __name__ == "__main__":
    main()
