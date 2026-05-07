import logging
from typing import List, Optional
from playwright.sync_api import sync_playwright, Page
from dataclasses import dataclass, asdict
import pandas as pd
import argparse
import platform
import time
import os

from normalize_names import normalize_csv
from remove_duplicates import remove_duplicates

@dataclass
class Place:
    name: str = ""
    address: str = ""
    website: str = ""
    phone_number: str = ""
    reviews_count: Optional[int] = None
    reviews_average: Optional[float] = None
    store_shopping: str = "No"
    in_store_pickup: str = "No"
    store_delivery: str = "No"
    place_type: str = ""
    opens_at: str = ""
    introduction: str = ""

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )

def extract_text(page: Page, xpath: str) -> str:
    try:
        if page.locator(xpath).count() > 0:
            return page.locator(xpath).inner_text()
    except Exception as e:
        logging.warning(f"Failed to extract text for xpath {xpath}: {e}")
    return ""

def extract_place(page: Page) -> Place:
    # XPaths
    name_xpath = '//div[@class="TIHn2 "]//h1[@class="DUwDvf lfPIob"]'
    address_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
    website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
    phone_number_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
    reviews_count_xpath = '//div[@class="TIHn2 "]//div[@class="fontBodyMedium dmRWX"]//div//span//span//span[@aria-label]'
    reviews_average_xpath = '//div[@class="TIHn2 "]//div[@class="fontBodyMedium dmRWX"]//div//span[@aria-hidden]'
    info1 = '//div[@class="LTs0Rc"][1]'
    info2 = '//div[@class="LTs0Rc"][2]'
    info3 = '//div[@class="LTs0Rc"][3]'
    opens_at_xpath = '//button[contains(@data-item-id, "oh")]//div[contains(@class, "fontBodyMedium")]'
    opens_at_xpath2 = '//div[@class="MkV9"]//span[@class="ZDu9vd"]//span[2]'
    place_type_xpath = '//div[@class="LBgpqf"]//button[@class="DkEaL "]'
    intro_xpath = '//div[@class="WeS02d fontBodyMedium"]//div[@class="PYvSYb "]'

    place = Place()
    place.name = extract_text(page, name_xpath)
    place.address = extract_text(page, address_xpath)
    place.website = extract_text(page, website_xpath)
    place.phone_number = extract_text(page, phone_number_xpath)
    place.place_type = extract_text(page, place_type_xpath)
    place.introduction = extract_text(page, intro_xpath) or "None Found"

    # Reviews Count
    reviews_count_raw = extract_text(page, reviews_count_xpath)
    if reviews_count_raw:
        try:
            temp = reviews_count_raw.replace('\xa0', '').replace('(','').replace(')','').replace(',','')
            place.reviews_count = int(temp)
        except Exception as e:
            logging.warning(f"Failed to parse reviews count: {e}")
    # Reviews Average
    reviews_avg_raw = extract_text(page, reviews_average_xpath)
    if reviews_avg_raw:
        try:
            temp = reviews_avg_raw.replace(' ','').replace(',','.')
            place.reviews_average = float(temp)
        except Exception as e:
            logging.warning(f"Failed to parse reviews average: {e}")
    # Store Info
    for idx, info_xpath in enumerate([info1, info2, info3]):
        info_raw = extract_text(page, info_xpath)
        if info_raw:
            temp = info_raw.split('·')
            if len(temp) > 1:
                check = temp[1].replace("\n", "").lower()
                if 'shop' in check:
                    place.store_shopping = "Yes"
                if 'pickup' in check:
                    place.in_store_pickup = "Yes"
                if 'delivery' in check:
                    place.store_delivery = "Yes"
    # Opens At
    opens_at_raw = extract_text(page, opens_at_xpath)
    if opens_at_raw:
        opens = opens_at_raw.split('⋅')
        if len(opens) > 1:
            place.opens_at = opens[1].replace("\u202f","")
        else:
            place.opens_at = opens_at_raw.replace("\u202f","")
    else:
        opens_at2_raw = extract_text(page, opens_at_xpath2)
        if opens_at2_raw:
            opens = opens_at2_raw.split('⋅')
            if len(opens) > 1:
                place.opens_at = opens[1].replace("\u202f","")
            else:
                place.opens_at = opens_at2_raw.replace("\u202f","")
    return place

def dismiss_consent(page: Page):
    """Try to dismiss any Google consent/cookie dialogs that may appear."""
    consent_selectors = [
        'button:has-text("Accept all")',
        'button:has-text("Reject all")',
        'button:has-text("I agree")',
        'button:has-text("Accept")',
        'form[action*="consent"] button',
        '[aria-label="Accept all"]',
    ]
    for selector in consent_selectors:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=2000):
                btn.click()
                logging.info(f"Dismissed consent dialog using: {selector}")
                page.wait_for_timeout(2000)
                return
        except Exception:
            continue

def find_and_fill_search_box(page: Page, search_for: str):
    """Find the Google Maps search box using multiple strategies and fill it."""
    # Strategy 1: original ID selector
    search_selectors = [
        '#searchboxinput',
        'input[aria-label="Search Google Maps"]',
        'input[name="q"]',
        'input[placeholder="Search Google Maps"]',
        'input.searchboxinput',
    ]
    for selector in search_selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=5000):
                locator.click()
                locator.fill(search_for)
                logging.info(f"Filled search box using selector: {selector}")
                return
        except Exception:
            continue

    # Strategy 2: find any visible text input on the page
    try:
        inputs = page.locator('input[type="text"], input:not([type])').all()
        for inp in inputs:
            if inp.is_visible():
                inp.click()
                inp.fill(search_for)
                logging.info("Filled search box using generic input fallback")
                return
    except Exception:
        pass

    raise Exception("Could not find the Google Maps search box with any known selector")

def scrape_places(search_for: str, total: int,
                  lat: float = None, lng: float = None, zoom: int = 13) -> List[Place]:
    setup_logging()
    places: List[Place] = []
    with sync_playwright() as p:
        if platform.system() == "Windows":
            browser_path = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
            browser = p.chromium.launch(executable_path=browser_path, headless=False)
        else:
            browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            if lat is not None and lng is not None:
                # Grid mode: navigate directly to pinned coordinate search
                query_encoded = search_for.replace(" ", "+")
                url = f"https://www.google.com/maps/search/{query_encoded}/@{lat},{lng},{zoom}z"
                page.goto(url, timeout=60000)
                page.wait_for_timeout(3000)
                dismiss_consent(page)
            else:
                # Legacy city-name mode
                page.goto("https://www.google.com/maps/@32.9817464,70.1930781,3.67z?", timeout=60000)
                page.wait_for_timeout(3000)
                dismiss_consent(page)
                find_and_fill_search_box(page, search_for)
                page.keyboard.press("Enter")
                page.wait_for_timeout(3000)

            # Wait for first result — 15 s is enough; empty grid points bail quickly
            try:
                page.wait_for_selector(
                    '//a[contains(@href, "https://www.google.com/maps/place")]',
                    timeout=15000,
                )
            except Exception:
                logging.info("No results at this location — skipping.")
                return places

            page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')
            previously_counted = 0
            while True:
                page.mouse.wheel(0, 10000)
                page.wait_for_timeout(2000)
                page.wait_for_selector(
                    '//a[contains(@href, "https://www.google.com/maps/place")]',
                    timeout=10000,
                )
                found = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count()
                logging.info(f"Currently Found: {found}")
                if found >= total:
                    break
                if found == previously_counted:
                    logging.info("Arrived at all available")
                    break
                previously_counted = found
            listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()[:total]
            listings = [listing.locator("xpath=..") for listing in listings]
            logging.info(f"Total Found: {len(listings)}")
            for idx, listing in enumerate(listings):
                try:
                    listing.click()
                    page.wait_for_selector('//div[@class="TIHn2 "]//h1[@class="DUwDvf lfPIob"]', timeout=10000)
                    time.sleep(1.5)  # Give time for details to load
                    place = extract_place(page)
                    if place.name:
                        places.append(place)
                    else:
                        logging.warning(f"No name found for listing {idx+1}, skipping.")
                except Exception as e:
                    logging.warning(f"Failed to extract listing {idx+1}: {e}")
        finally:
            browser.close()
    return places

def save_places_to_csv(places: List[Place], output_path: str = "result.csv", append: bool = False):
    df = pd.DataFrame([asdict(place) for place in places])
    if not df.empty:
        # Only drop columns that are all identical AND contain a useless default value.
        # Skip this entirely when there's only 1 row (every column would be "unique == 1").
        if len(df) > 1:
            default_values = {"", "No", "None Found"}
            for column in list(df.columns):
                if df[column].nunique() == 1:
                    val = df[column].iloc[0]
                    if pd.isna(val) or str(val).strip() in default_values:
                        df.drop(column, axis=1, inplace=True)
        file_exists = os.path.isfile(output_path)
        mode = "a" if append else "w"
        header = not (append and file_exists)
        df.to_csv(output_path, index=False, mode=mode, header=header)
        logging.info(f"Saved {len(df)} places to {output_path} (append={append})")
    else:
        logging.warning("No data to save. DataFrame is empty.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--search", type=str, help="Search query for Google Maps")
    parser.add_argument("-t", "--total", type=int, help="Total number of results to scrape")
    parser.add_argument("-o", "--output", type=str, default="result.csv", help="Output CSV file path")
    parser.add_argument("--append", action="store_true", help="Append results to the output file instead of overwriting")
    args = parser.parse_args()
    search_for = args.search or "turkish stores in toronto Canada"
    total = args.total or 1
    output_path = args.output
    append = args.append
    places = scrape_places(search_for, total)
    save_places_to_csv(places, output_path, append=append)

    logging.info("Running name normalization...")
    normalize_csv(output_path, output_path)

    logging.info("Removing duplicates...")
    remove_duplicates(output_path, output_path)

if __name__ == "__main__":
    main()
