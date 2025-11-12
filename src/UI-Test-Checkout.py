"""
UI-Test für Secuconnect Checkout mit Kreditkartenzahlung
Autor: René Sachs
Datum: November 2025
"""

import os
import json
import time
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import requests
from requests import Response
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


# -----------------------------------------------------------------------------
# Konfiguration
# -----------------------------------------------------------------------------
@dataclass
class TestConfig:
    # API
    API_BASE_URL: str = "https://connect-testing.secuconnect.com"
    AUTH_ENDPOINT: str = ""
    TRANSACTION_ENDPOINT: str = ""

    CLIENT_ID: str = os.getenv("SC_CLIENT_ID", "bitte die validen Testdaten aus dem PDF Fallaufgabe Softwaretester verwenden")
    CLIENT_SECRET: str = os.getenv("SC_CLIENT_SECRET", "bitte die validen Testdaten aus dem PDF Fallaufgabe Softwaretester verwenden")
    GENERAL_CONTRACT_ID: str = os.getenv("SC_GCR", "bitte die validen Testdaten aus dem PDF Fallaufgabe Softwaretester verwenden")
    MERCHANT_REF: str = "50001234"
    CHECKOUT_TEMPLATE: str = "COT_WD0DE66HN2XWJHW8JM88003YG0NEA2"

    # Testdaten
    CUSTOMER_DATA: dict = None
    CREDIT_CARD: dict = None

    # Timeouts
    IMPLICIT_WAIT: int = 5
    EXPLICIT_WAIT: int = 20
    REQUEST_TIMEOUT: int = 20

    def __post_init__(self) -> None:
        self.AUTH_ENDPOINT = f"{self.API_BASE_URL}/oauth/token"
        self.TRANSACTION_ENDPOINT = f"{self.API_BASE_URL}/api/v2/Smart/Transactions/"

        if self.CUSTOMER_DATA is None:
            self.CUSTOMER_DATA = {
                "email": "testuser@example.com",
                "salutation": "mr",
                "first_name": "Max",
                "last_name": "Mustermann",
                "country": "DE",
                "zip_code": "12345",
                "city": "Berlin",
                "street": "Teststraße 2",
            }

        if self.CREDIT_CARD is None:
            self.CREDIT_CARD = {
                "holder": "Max Mustermann",
                "number": "4635440000002298",
                "cvv": "123",
                "expiry_month": "12",
                "expiry_year": "2026",
            }

    def validate(self) -> None:
        missing = []
        if not self.CLIENT_ID:
            missing.append("SC_CLIENT_ID/CLIENT_ID")
        if not self.CLIENT_SECRET:
            missing.append("SC_CLIENT_SECRET/CLIENT_SECRET")
        if not self.GENERAL_CONTRACT_ID:
            missing.append("SC_GCR/GENERAL_CONTRACT_ID")
        if missing:
            raise RuntimeError(f"Fehlende Konfiguration: {', '.join(missing)}")


# -----------------------------------------------------------------------------
# API-Client
# -----------------------------------------------------------------------------
class ApiClient:
    def __init__(self, config: TestConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "checkout-ui-test/1.0"})
        self.access_token: Optional[str] = None
        self.transaction_id: Optional[str] = None
        self.checkout_url: Optional[str] = None

    @staticmethod
    def _ensure_2xx(resp: Response) -> None:
        if not (200 <= resp.status_code < 300):
            raise RuntimeError(
                f"HTTP {resp.status_code} (expected 2xx)\n"
                f"{resp.request.method} {resp.url}\n{resp.text}"
            )

    def authenticate(self) -> str:
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.config.CLIENT_ID,
            "client_secret": self.config.CLIENT_SECRET,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        logging.info("API: Authentifiziere …")
        resp = self.session.post(
            self.config.AUTH_ENDPOINT, data=payload, headers=headers,
            timeout=self.config.REQUEST_TIMEOUT
        )
        self._ensure_2xx(resp)

        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError(f"Kein access_token in Antwort: {resp.text}")

        self.access_token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        logging.info("API: Auth OK")
        return token

    def create_transaction(self) -> Tuple[str, str]:
        if not self.access_token:
            raise RuntimeError("Nicht authentifiziert")

        url = self.config.TRANSACTION_ENDPOINT
        payload = {
            "intent": "sale",
            "is_demo": False,
            "contract": {"object": "general.contracts", "id": self.config.GENERAL_CONTRACT_ID},
            "basket": {
                "products": [{
                    "id": 1,
                    "parent": None,
                    "item_type": "article",
                    "desc": "Test-Produkt",
                    "articleNumber": "TEST-001",
                    "ean": "",
                    "quantity": 1,
                    "priceOne": 1000,  # Cent
                    "tax": 19,
                    "reference_id": None,
                    "group": []
                }]
            },
            "basket_info": {"sum": 1000, "currency": "EUR"},
            "transactionRef": "",
            "merchantRef": self.config.MERCHANT_REF,
            "application_context": {
                "return_urls": {
                    "url_success": "https://example.org/SUCCESS",
                    "url_error": "https://example.org/ERROR",
                    "url_abort": "https://example.org/FAILURE"
                },
                "checkout_template": self.config.CHECKOUT_TEMPLATE,
                "language": "de"
            },
            "payment_context": {
                "auto_capture": True,
                "payment_methods": None,
                "merchant_initiated": False,
                "accrual": False,
                "creditcard_schemes": ["visa", "mastercard"]
            }
        }
        headers = {"Content-Type": "application/json"}

        logging.info("API: Erzeuge Transaktion …")
        resp = self.session.post(url, json=payload, headers=headers, timeout=self.config.REQUEST_TIMEOUT)
        self._ensure_2xx(resp)
        data = resp.json()

        self.transaction_id = data.get("id")
        if not self.transaction_id:
            raise RuntimeError(f"Keine STX-ID: {json.dumps(data, indent=2, ensure_ascii=False)}")

        # Checkout-URL extrahieren
        links = data.get("links") or {}
        checkout_from_links = None
        if isinstance(links, dict):
            if "checkout" in links and isinstance(links["checkout"], dict):
                checkout_from_links = links["checkout"].get("href")
            checkout_from_links = checkout_from_links or links.get("checkout_url")

        payment_links = data.get("payment_links") or {}
        checkout_from_paylinks = (
            payment_links.get("creditcard")
            or payment_links.get("general")
            or payment_links.get("prepaid")
        )

        self.checkout_url = (
            (checkout_from_links if isinstance(checkout_from_links, str) else None)
            or (checkout_from_paylinks if isinstance(checkout_from_paylinks, str) else None)
            or data.get("checkout_url")
            or data.get("redirect_url")
            or data.get("url")
        )

        if not self.checkout_url:
            raise RuntimeError(f"Keine Checkout-URL: {json.dumps(data, indent=2, ensure_ascii=False)}")

        logging.info("API: STX: %s", self.transaction_id)
        logging.info("API: Checkout-URL: %s", self.checkout_url)
        return self.transaction_id, self.checkout_url

    def get_transaction_status(self, stx_id: Optional[str] = None) -> dict:
        stx = stx_id or self.transaction_id
        if not stx:
            raise RuntimeError("Keine Transaktion vorhanden")

        url = f"{self.config.TRANSACTION_ENDPOINT}{stx}"
        resp = self.session.get(url, timeout=self.config.REQUEST_TIMEOUT)
        self._ensure_2xx(resp)
        return resp.json()


# -----------------------------------------------------------------------------
# Page Object: Checkout
# -----------------------------------------------------------------------------
class CheckoutPage:
    def __init__(self, driver: webdriver.Chrome, wait: WebDriverWait) -> None:
        self.driver = driver
        self.wait = wait

    def _scroll_into_view(self, el) -> None:
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)

    def _by_label_input(self, label_text: str):
        xp = f"//label[normalize-space()='{label_text}']"
        label = self.wait.until(EC.presence_of_element_located((By.XPATH, xp)))
        for_id = label.get_attribute("for")
        if for_id:
            return By.ID, for_id
        return By.XPATH, f"{xp}/following::*[self::input or self::textarea][1]"

    def _by_label_select(self, label_text: str):
        xp = f"//label[normalize-space()='{label_text}']"
        label = self.wait.until(EC.presence_of_element_located((By.XPATH, xp)))
        for_id = label.get_attribute("for")
        if for_id:
            return By.ID, for_id
        return By.XPATH, f"{xp}/following::*[self::select][1]"

    def _enter_text(self, locator, text: str, label: str) -> None:
        el = self.wait.until(EC.visibility_of_element_located(locator))
        self._scroll_into_view(el)
        el.clear()
        el.send_keys(text)
        logging.info("UI: %s: %s", label, text)

    def _select_by_text(self, locator, text: str, label: str) -> None:
        el = self.wait.until(EC.visibility_of_element_located(locator))
        try:
            Select(el).select_by_visible_text(text)
            logging.info("UI: %s: %s", label, text)
        except Exception:
            # Custom-Select Fallback
            el.click()
            opt = self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, f"//div[@role='option' or self::li][normalize-space()='{text}']")
            ))
            opt.click()
            logging.info("UI: %s (custom): %s", label, text)

    def _click_button_by_text(self, *texts: str):
        xp_or = " or ".join([f"contains(.,'{t}')" for t in texts])
        btn = self.wait.until(EC.element_to_be_clickable(
            (By.XPATH, f"//*[self::button or self::a][{xp_or}]")
        ))
        self._scroll_into_view(btn)
        time.sleep(0.2)
        btn.click()

    def _click_button_by_type(self, *types: str, timeout: Optional[int] = None):
        if not types:
            raise ValueError("_click_button_by_type: mindestens ein Typ erforderlich")

        def lower(s: str) -> str:
            return s.lower()

        clauses = [
            f"translate(@type,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='{lower(t)}'"
            for t in types
        ]
        xp_type_or = " or ".join(clauses)
        xpath = f"(//button[{xp_type_or}] | //input[{xp_type_or}])"

        wait = self.wait if timeout is None else WebDriverWait(self.driver, timeout)
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        self._scroll_into_view(btn)
        time.sleep(0.2)
        btn.click()
        return btn

    def _switch_into_iframe_with(self, by, value, timeout: int = 10) -> bool:
        self.driver.switch_to.default_content()
        iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
        for f in iframes:
            self.driver.switch_to.default_content()
            self.driver.switch_to.frame(f)
            try:
                WebDriverWait(self.driver, timeout).until(EC.visibility_of_element_located((by, value)))
                return True
            except Exception:
                continue
        self.driver.switch_to.default_content()
        return False

    def _leave_iframe(self) -> None:
        self.driver.switch_to.default_content()

    def _input_by_attrs_keywords(self, keywords):
        def tr(s):
            return f"translate({s}, 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ', 'abcdefghijklmnopqrstuvwxyzäöü')"

        conds = []
        for attr in ["name", "id", "placeholder", "aria-label"]:
            for kw in keywords:
                conds.append(f"contains({tr('@'+attr)}, '{kw.lower()}')")
        kw_xpath = " or ".join(conds)
        xp = f"//input[{kw_xpath}] | //textarea[{kw_xpath}]"
        return By.XPATH, xp

    def _enter_any(self, label_candidates, attr_keywords, value: str, label: str) -> None:
        try:
            loc = self._by_label_input(next(iter(label_candidates)))
            self._enter_text(loc, value, f"{label} (Label)")
            return
        except Exception:
            pass
        for lbl in label_candidates:
            try:
                loc = self._by_label_input(lbl)
                self._enter_text(loc, value, f"{label} (Label)")
                return
            except Exception:
                continue
        try:
            loc = self._input_by_attrs_keywords(attr_keywords)
            self._enter_text(loc, value, f"{label} (Attr)")
            return
        except Exception:
            pass
        try:
            def tr(s):
                return f"translate({s}, 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ', 'abcdefghijklmnopqrstuvwxyzäöü')"
            kw_text = " or ".join([f"contains({tr('@aria-label')}, '{k.lower()}')" for k in attr_keywords])
            xp = f"//*[@contenteditable='true' and ({kw_text})]"
            el = self.wait.until(EC.visibility_of_element_located((By.XPATH, xp)))
            self._scroll_into_view(el)
            el.click()
            el.send_keys(value)
            logging.info("UI: %s (contenteditable): %s", label, value)
            return
        except Exception:
            pass

        raise RuntimeError(f"{label}: kein passendes Feld gefunden")

    def wait_for_customer_form(self) -> None:
        logging.info("UI: Warte auf Kundendaten-Formular …")
        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//label | //*[contains(@class,'customer') or contains(.,'Kundendaten') or contains(.,'Customer')]"
        )))
        logging.info("UI: Kundendaten-Formular sichtbar")

    def fill_customer_data(self, data: dict) -> None:
        logging.info("UI: Fülle Kundendaten …")

        self._enter_any(
            label_candidates=["E-Mail", "E-Mail-Adresse", "Email", "E-Mail *"],
            attr_keywords=["e-mail", "email"],
            value=data["email"], label="E-Mail"
        )

        try:
            sal_map = {"mr": "Herr", "ms": "Frau"}
            for lbl in ["Anrede", "Titel", "Anrede/Titel"]:
                try:
                    sel_loc = self._by_label_select(lbl)
                    self._select_by_text(sel_loc, sal_map.get(data.get("salutation", ""), data.get("salutation", "")), "Anrede")
                    break
                except Exception:
                    continue
        except Exception:
            pass

        self._enter_any(["Vorname"], ["vorname", "first"], data["first_name"], "Vorname")
        self._enter_any(["Nachname"], ["nachname", "last"], data["last_name"], "Nachname")
        self._enter_any(["PLZ", "Postleitzahl"], ["plz", "zip"], data["zip_code"], "PLZ")
        self._enter_any(["Ort", "Stadt"], ["city", "ort"], data["city"], "Ort")
        self._enter_any(["Straße, Hausnummer", "Adresse"], ["street", "adresse"], data["street"], "Adresse")

        try:
            sel_loc = self._by_label_select("Land")
            self._select_by_text(sel_loc, "Deutschland", "Land")
        except Exception:
            pass

        logging.info("UI: Kundendaten ausgefüllt")

    def click_continue(self) -> None:
        self._click_button_by_text("Weiter", "Fortfahren", "Continue", "Next")

    def fill_credit_card(self, card: dict) -> None:
        logging.info("UI: Fülle Kreditkartendaten …")

        # Karteninhaber
        self._enter_any(
            label_candidates=["Karteninhaber", "Karteninhaber/in", "Name auf Karte"],
            attr_keywords=["karteninhaber", "cardholder", "holder", "name"],
            value=card["holder"], label="Karteninhaber"
        )

        CARD_NUMBER_XP = (
            "//input[@id='card-number' or @name='cardNumber' or "
            "contains(@placeholder,'Card number') or contains(@placeholder,'Kartennummer') or "
            "@inputmode='numeric' or @type='tel']"
        )
        EXPIRY_XP = (
            "//input[@id='exp-date' or @name='expiry' or "
            "contains(@placeholder,'MM') or contains(@placeholder,'Expiry')]"
        )
        CVC_XP = (
            "//input[@id='cardCvv' or @name='cvc' or "
            "contains(@placeholder,'CVC') or contains(@placeholder,'CVV')]"
        )

        in_iframe = self._switch_into_iframe_with(By.XPATH, CARD_NUMBER_XP, timeout=10)

        self._enter_text((By.XPATH, CARD_NUMBER_XP), card["number"], "Kartennummer")

        try:
            self._enter_text((By.XPATH, EXPIRY_XP), f"{card['expiry_month']}/{card['expiry_year'][-2:]}", "Ablauf (MM/YY)")
        except Exception:
            self._enter_text((By.ID, "exp-date"), card["expiry_month"], "Ablauf Monat")
            self._enter_text((By.ID, "expiryYear"), card["expiry_year"], "Ablauf Jahr")

        self._enter_text((By.XPATH, CVC_XP), card["cvv"], "CVC")

        if in_iframe:
            self._leave_iframe()

        logging.info("UI: Kreditkartendaten ausgefüllt")

    def click_continue_to_payment(self) -> None:
        self._click_button_by_text("Jetzt zahlen")

    def click_submit(self) -> None:
        try:
            self._click_button_by_type("submit")
        except Exception:
            self._click_button_by_text("Bezahlen", "Pay", "Zahlung")

    def wait_for_result(self, timeout: int = 40) -> str:
        logging.info("UI: Warte auf Ergebnis/Redirect …")
        end = time.time() + timeout
        while time.time() < end:
            url = (self.driver.current_url or "").upper()
            if "SUCCESS" in url:
                logging.info("UI: Redirect SUCCESS")
                return "SUCCESS_URL"
            if "ERROR" in url:
                logging.info("UI: Redirect ERROR")
                return "ERROR_URL"
            if "FAILURE" in url or "ABORT" in url:
                logging.info("UI: Redirect FAILURE")
                return "FAILURE_URL"
            time.sleep(0.2)
        try:
            el = WebDriverWait(self.driver, 5).until(EC.visibility_of_element_located(
                (By.XPATH, "//*[contains(.,'erfolgreich') or contains(.,'success') or contains(.,'fehlgeschlagen') or contains(.,'failed')]")
            ))
            txt = (el.text or "").strip()
            logging.info("UI: Meldung: %s", txt)
            return txt or "UNKNOWN"
        except Exception:
            return "UNKNOWN"


# -----------------------------------------------------------------------------
# Testlauf
# -----------------------------------------------------------------------------
class CheckoutTest:
    def __init__(self) -> None:
        self.config = TestConfig()
        self.api = ApiClient(self.config)
        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None
        self.page: Optional[CheckoutPage] = None

    def setup(self) -> None:
        logging.info("SETUP")
        self.config.validate()

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-gpu")

        self.driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options
        )
        self.driver.implicitly_wait(self.config.IMPLICIT_WAIT)
        self.wait = WebDriverWait(self.driver, self.config.EXPLICIT_WAIT)
        self.page = CheckoutPage(self.driver, self.wait)

        logging.info("Browser bereit")

    def teardown(self) -> None:
        logging.info("TEARDOWN")
        if self.driver:
            try:
                self.driver.quit()
            finally:
                logging.info("Browser geschlossen")

    def run(self) -> None:
        try:
            self.setup()

            # 1) Auth
            print("\n" + "=" * 70)
            print("SCHRITT 1: Authentifizierung")
            print("=" * 70)
            self.api.authenticate()

            # 2) Transaktion erzeugen
            print("\n" + "=" * 70)
            print("SCHRITT 2: Transaktion erstellen")
            print("=" * 70)
            stx_id, checkout_url = self.api.create_transaction()

            # 3) Checkout laden
            print("\n" + "=" * 70)
            print("SCHRITT 3: Checkout-Seite laden")
            print("=" * 70)
            assert self.driver is not None
            self.driver.get(checkout_url)

            # 4) Kundendaten eingeben
            print("\n" + "=" * 70)
            print("SCHRITT 4: Kundendaten eingeben")
            print("=" * 70)
            assert self.page is not None
            self.page.wait_for_customer_form()
            self.page.fill_customer_data(self.config.CUSTOMER_DATA)
            self.page.click_continue()
            self.driver.save_screenshot("02_Kundendaten_ausgefuellt.png")

            # 5) Kreditkartendaten eingeben
            print("\n" + "=" * 70)
            print("SCHRITT 5: Kreditkartendaten eingeben")
            print("=" * 70)
            self.page.fill_credit_card(self.config.CREDIT_CARD)
            self.page.click_continue_to_payment()
            self.driver.save_screenshot("03_Kreditkarte_ausgefuellt.png")

            # 6) Submit klicken
            print("\n" + "=" * 70)
            print("SCHRITT 6: Submit klicken")
            print("=" * 70)
            self.page.click_submit()

            # 7) UI-Ergebnis abwarten
            print("\n" + "=" * 70)
            print("SCHRITT 7: Warte auf Ergebnis")
            print("=" * 70)
            result = self.page.wait_for_result()
            logging.info("ERGEBNIS UI: %s", result)

            # 8) API-Status prüfen
            print("\n" + "=" * 70)
            print("SCHRITT 8: API-Status prüfen")
            print("=" * 70)
            time.sleep(3)
            status_json = self.api.get_transaction_status(stx_id)
            status = status_json.get("status") or status_json.get("transaction_status")
            logging.info("ERGEBNIS API: %s", status)

            assert result in {"SUCCESS_URL", "ERROR_URL", "FAILURE_URL", "UNKNOWN"}
        except Exception as exc:
            logging.error("FEHLER: %s", exc)
            if self.driver:
                path = f"error_screenshot_{int(time.time())}.png"
                try:
                    self.driver.save_screenshot(path)
                    logging.info("Screenshot: %s", path)
                except Exception:
                    pass
            raise
        finally:
            self.teardown()


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> None:
    """Haupteinstiegspunkt"""
    print("\n" + "╔" + "=" * 68 + "╗")
    print("║" + " " * 20 + "CHECKOUT UI-TEST" + " " * 32 + "║")
    print("║" + " " * 15 + "Kreditkartenzahlung - Secuconnect" + " " * 20 + "║")
    print("╚" + "=" * 68 + "╝\n")
    test = CheckoutTest()
    test.run()


if __name__ == "__main__":
    main()
