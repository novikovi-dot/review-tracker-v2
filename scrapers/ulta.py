import pandas as pd
import requests
import re
import time
import urllib3
from io import BytesIO

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_KEY = "daa0f241-c242-4483-afb7-4449942d1a2b"


def clean_filename(text):
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"www\.ulta\.com/p/", "", text)
    text = text.split("?")[0]
    text = text.split("#")[0]
    text = re.sub(r"-pimprod\d+", "", text)
    text = re.sub(r"-xlsImpprod\d+", "", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text)
    text = text.strip("_")

    if not text:
        return "ulta_reviews"

    return text[:120]


def extract_possible_ids(link):
    ids = []

    pimprod_match = re.search(r"pimprod\d+", link)
    impprod_match = re.search(r"[a-zA-Z]*[iI]mpprod\d+", link)
    mkt_match = re.search(r"mkt\d+", link)
    sku_match = re.search(r"sku=(\d+)", link)

    if pimprod_match:
        ids.append(pimprod_match.group(0))

    if impprod_match:
        ids.append(impprod_match.group(0))

    if mkt_match:
        ids.append(mkt_match.group(0))

    if sku_match:
        ids.append(sku_match.group(1))

    return ids


def get_property(details, property_key):
    properties = details.get("properties", [])

    for prop in properties:
        if prop.get("key") == property_key:
            values = prop.get("value", [])
            if values:
                return values[0]

    return ""


def make_request(url, params):
    for attempt in range(5):
        try:
            response = requests.get(
                url,
                params=params,
                verify=False,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0"}
            )

            if response.status_code == 200:
                return response

            if response.status_code in [429, 500, 502, 503, 504]:
                wait_time = 8 + attempt * 8
                time.sleep(wait_time)
                continue

            return None

        except requests.exceptions.RequestException:
            wait_time = 8 + attempt * 8
            time.sleep(wait_time)

    return None


def scrape_reviews(product_id, delay_seconds, review_progress_bar=None, review_progress_text=None):
    all_reviews = []

    base_url = "https://display.powerreviews.com"
    next_url = f"{base_url}/m/6406/l/en_US/product/{product_id}/reviews"

    params = {
        "apikey": API_KEY,
        "_noconfig": "true",
        "sort": "Newest",
        "image_only": "false",
        "page_locale": "en_US"
    }

    total_results = None

    while next_url:
        response = make_request(next_url, params)

        if response is None:
            break

        data = response.json()

        results = data.get("results", [])
        if not results:
            break

        reviews = results[0].get("reviews", [])
        if not reviews:
            break

        if total_results is None:
            total_results = data.get("paging", {}).get("total_results", 0)

        for review in reviews:
            details = review.get("details", {})
            metrics = review.get("metrics", {})

            all_reviews.append({
                "matched_id": product_id,
                "review_id": review.get("review_id", ""),
                "rating": metrics.get("rating", ""),
                "review_title": details.get("headline", ""),
                "review_text": details.get("comments", ""),
                "reviewer_name": details.get("nickname", ""),
                "location": review.get("location", ""),
                "created_date": review.get("created_date", ""),
                "helpful_votes": metrics.get("helpful_votes", ""),
                "not_helpful_votes": metrics.get("not_helpful_votes", ""),
                "hair_type": get_property(details, "hairtype"),
            })

        if total_results and review_progress_bar is not None and review_progress_text is not None:
            progress = min(len(all_reviews) / total_results, 1.0)
            review_progress_bar.progress(progress)
            review_progress_text.write(
                f"Downloaded {len(all_reviews):,} of {total_results:,} reviews..."
            )

        next_page_url = data.get("paging", {}).get("next_page_url")

        if next_page_url:
            next_url = base_url + next_page_url
            params = {
                "apikey": API_KEY,
                "_noconfig": "true"
            }
        else:
            next_url = None

        time.sleep(delay_seconds)

    return pd.DataFrame(all_reviews)


def scrape_product(link, delay_seconds, review_progress_bar=None, review_progress_text=None):
    possible_ids = extract_possible_ids(link)

    if not possible_ids:
        return None, None

    for product_id in possible_ids:
        df = scrape_reviews(
            product_id,
            delay_seconds,
            review_progress_bar,
            review_progress_text
        )

        if df is not None and not df.empty:
            return df, product_id

    return None, None


def create_excel_file(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Reviews")

        worksheet = writer.sheets["Reviews"]

        widths = {
            "A": 25,
            "B": 18,
            "C": 10,
            "D": 45,
            "E": 100,
            "F": 25,
            "G": 25,
            "H": 20,
            "I": 18,
            "J": 20,
            "K": 20,
        }

        for column, width in widths.items():
            worksheet.column_dimensions[column].width = width

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

        for row in worksheet.iter_rows():
            for cell in row:
                cell.alignment = cell.alignment.copy(
                    wrap_text=True,
                    vertical="top"
                )

    output.seek(0)
    return output
