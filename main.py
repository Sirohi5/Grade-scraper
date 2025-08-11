import os
import json
import pandas as pd
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from dotenv import load_dotenv

# ---------- config / env ----------
load_dotenv()
LOGIN_URL = os.getenv("LOGIN_URL", "https://demo-login.uninow.io/")
USERNAME  = os.getenv("USERNAME", "student")
PASSWORD  = os.getenv("PASSWORD", "password123")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------- helpers ----------
def setup_driver():
    opts = Options()
    # make it visible while debugging; switch on headless later if you like
    # opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1280,900")
    return webdriver.Chrome(options=opts)

def save_debug(driver, tag):
    """Dump a screenshot + html snapshot to output/ for debugging."""
    try:
        driver.save_screenshot(str(OUTPUT_DIR / f"{tag}.png"))
        with open(OUTPUT_DIR / f"{tag}.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
    except Exception:
        pass

def js_click(driver, element):
    driver.execute_script("arguments[0].click();", element)

# ---------- scraping flow ----------
def login(driver):
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 20)

    # Try several robust selectors for the "Easy/Einfaches Login" control
    login_selectors = [
        # German button or link
        (By.XPATH, "//*[self::button or self::a][contains(translate(normalize-space(.),"
                   " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
                   " 'einfaches login')]"),
        # English fallback
        (By.XPATH, "//*[self::button or self::a][contains(translate(normalize-space(.),"
                   " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
                   " 'easy login')]"),
        # Any control with 'Login' that sits in the first choice panel (broad fallback)
        (By.XPATH, "(//*[self::button or self::a][contains(., 'Login')])[1]")
    ]

    easy = None
    last_err = None
    for by, sel in login_selectors:
        try:
            easy = wait.until(EC.visibility_of_element_located((by, sel)))
            break
        except TimeoutException as e:
            last_err = e
            continue

    if easy is None:
        save_debug(driver, "fail_before_click_easy_login")
        raise TimeoutException("Could not find the 'Einfaches/Easy Login' control.") from last_err

    # Try JS click first (more reliable if overlays exist)
    try:
        js_click(driver, easy)
    except Exception:
        try:
            easy.click()
        except Exception:
            ActionChains(driver).move_to_element(easy).click().perform()

    # Now wait for the username/password form
    try:
        user_input = wait.until(EC.presence_of_element_located((By.NAME, "username")))
    except TimeoutException:
        save_debug(driver, "fail_waiting_for_credentials")
        raise

    pwd_input  = driver.find_element(By.NAME, "password")

    user_input.clear(); user_input.send_keys(USERNAME)
    pwd_input.clear();  pwd_input.send_keys(PASSWORD)

    # Find and click Anmelden (Login) button (German/English tolerant)
    submit = None
    for by, sel in [
        (By.XPATH, "//button[contains(., 'Anmelden')]"),
        (By.XPATH, "//button[contains(., 'Login')]"),
        (By.XPATH, "//*[self::button or self::a][contains(., 'Anmelden') or contains(., 'Login')]")
    ]:
        try:
            submit = driver.find_element(by, sel)
            break
        except NoSuchElementException:
            continue

    if submit is None:
        save_debug(driver, "fail_no_submit_button")
        raise NoSuchElementException("Could not find the login submit button.")

    try:
        js_click(driver, submit)
    except Exception:
        submit.click()

    # Wait for the "Noten anzeigen" button to guarantee login success
    try:
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[self::button or self::a][contains(., 'Noten anzeigen')]")))
    except TimeoutException:
        save_debug(driver, "fail_after_login_no_grades_button")
        raise

def go_to_grades(driver):
    wait = WebDriverWait(driver, 20)
    grades_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[self::button or self::a][contains(., 'Noten anzeigen')]")))
    try:
        js_click(driver, grades_btn)
    except Exception:
        grades_btn.click()
    wait.until(EC.presence_of_element_located((By.XPATH, "//table")))

def extract_grades(driver):
    grades = []
    # skip header
    rows = driver.find_elements(By.XPATH, "//table//tr")[1:]
    for r in rows:
        tds = r.find_elements(By.TAG_NAME, "td")
        if len(tds) >= 7:
            def txt(i): return tds[i].text.strip()
            # normalize decimal comma in notes
            note_txt = txt(4).replace(",", ".")
            try:
                note_val = float(note_txt)
            except ValueError:
                note_val = None
            try:
                credits_val = int(txt(5))
            except ValueError:
                credits_val = None
            grades.append({
                "Titel":   txt(0),
                "Modul":   txt(1),
                "Semester":txt(2),
                "Datum":   txt(3),
                "Note":    note_val,
                "Credits": credits_val,
                "Status":  txt(6)
            })
    return grades

def extract_summary(driver):
    def get_value(label):
        # label div followed by value div
        xpath = f"//div[contains(., '{label}')]/following-sibling::div"
        el = driver.find_element(By.XPATH, xpath)
        return el.text.strip()

    summary = {}
    try:
        avg = get_value("Gesamtdurchschnitt").replace(",", ".")
        summary["Gesamtdurchschnitt"] = float(avg)
    except Exception:
        summary["Gesamtdurchschnitt"] = None

    try:
        summary["Credits erhalten"] = get_value("Credits erhalten")
    except Exception:
        summary["Credits erhalten"] = None

    try:
        summary["Bestandene Prüfungen"] = get_value("Bestandene Prüfungen")
    except Exception:
        summary["Bestandene Prüfungen"] = None

    return summary

def save_output(grades, summary, fmt="json"):
    OUTPUT_DIR.mkdir(exist_ok=True)
    if fmt == "json":
        with open(OUTPUT_DIR / "grades.json", "w", encoding="utf-8") as f:
            json.dump({"grades": grades, "summary": summary}, f, indent=2, ensure_ascii=False)
    else:
        pd.DataFrame(grades).to_csv(OUTPUT_DIR / "grades.csv", index=False)
        with open(OUTPUT_DIR / "summary.txt", "w", encoding="utf-8") as f:
            for k, v in summary.items():
                f.write(f"{k}: {v}\n")

def main(fmt="json"):
    driver = setup_driver()
    try:
        login(driver)
        go_to_grades(driver)
        grades = extract_grades(driver)
        summary = extract_summary(driver)
        save_output(grades, summary, fmt)
        print(f"✅ Saved to output/ as {fmt}")
    finally:
        driver.quit()

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--format", choices=["json", "csv"], default="json")
    args = p.parse_args()
    main(args.format)
