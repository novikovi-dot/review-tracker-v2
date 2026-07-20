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
    text = re.sub(r"-(pimprod|mkt|xlsImpprod)\d+", "", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text)
    text = text.strip("_")
    return text[:120] if text else "ulta_reviews"


def extract_possible_ids(link):
    ids = []

    patterns = [
        r"pimprod\d+",
        r"mkt\d+",
        r"[a-zA-Z]*[iI]mpprod\d+",
        r"sku=(\d+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            ids.append(match.group(1) if match.groups() else match.group(0))

    return list(dict.fromkeys(ids))


def get_property(details, property_key):
    for prop in details.get("properties", []):
        if prop.get("key") == property_key:
            values = prop.get("value", [])
            return values[0] if values else ""
    return ""

def detect_incentivized_review(review_text):
    if not review_text:
        return False

    normalized_text = str(review_text).lower().strip()

    disclosure_phrases = [
        "i received this product in exchange for my honest review",
        "received this product in exchange for my honest review",
        "in exchange for my honest review",
        "received this product for free",
        "received this product complimentary",
        "received this complimentary",
        "complimentary product",
        "gifted this product",
        "gifted by",
        "free product",
        "product was provided to me",
        "product was sent to me",
        "received this product to review",
        "received this item to review",
        "influenster"
    ]

    return any(
        phrase in normalized_text
        for phrase in disclosure_phrases
    )


def extract_review_date(review, details):
    possible_dates = [
        review.get("created_date"),
        review.get("review_date"),
        review.get("submission_time"),
        review.get("submission_date"),
        review.get("date"),
        details.get("created_date"),
        details.get("review_date"),
        details.get("submission_time"),
        details.get("submission_date"),
        details.get("date")
    ]

    for value in possible_dates:
        if value is not None and str(value).strip() != "":
            return value

    return None

def make_request(url, params):
    for attempt in range(5):
        try:
            response = requests.get(
                url,
                params=params,
                verify=False,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json"
                }
            )

            if response.status_code == 200:
                return response

            if response.status_code in [429, 500, 502, 503, 504]:
                time.sleep(8 + attempt * 8)
                continue

            return None

        except requests.exceptions.RequestException:
            time.sleep(8 + attempt * 8)

    return None

def detect_incentivized_review(review_text):
    if not review_text:
        return False

    normalized_text = str(review_text).lower().strip()

    disclosure_phrases = [
        "i received this product in exchange for my honest review",
        "received this product in exchange for my honest review",
        "in exchange for my honest review",
        "received this product for free",
        "received this product complimentary",
        "received this complimentary",
        "complimentary product",
        "gifted this product",
        "gifted by",
        "free product",
        "product was provided to me",
        "product was sent to me",
        "received this product to review",
        "received this item to review"
    ]

    return any(
        phrase in normalized_text
        for phrase in disclosure_phrases
    )

def scrape_reviews(product_id, delay_seconds, review_progress_bar=None, review_progress_text=None):
    all_reviews = []
    official_recommendation_rate = ""

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

        rollup = results[0].get("rollup", {})
        recommended_ratio = rollup.get("recommended_ratio")

        if recommended_ratio not in [None, ""]:
            official_recommendation_rate = f"{round(float(recommended_ratio) * 100)}%"

        reviews = results[0].get("reviews", [])
        if not reviews:
            break

        if total_results is None:
            total_results = data.get("paging", {}).get("total_results", 0)

        for review in reviews:
            details = review.get("details", {}) or {}
            metrics = review.get("metrics", {}) or {}

            review_text = details.get("comments", "") or ""
            review_date = extract_review_date(
                review,
                details
            )

            all_reviews.append({
                "matched_id": product_id,
                "review_id": review.get("review_id", ""),
                "rating": metrics.get("rating", ""),
                "review_title": details.get("headline", ""),
                "review_text": review_text,
                "reviewer_name": details.get("nickname", ""),
                "location": (
                    review.get("location")
                    or details.get("location", "")
                ),
                "review_date": review_date,
                "helpful_votes": metrics.get(
                    "helpful_votes",
                    ""
                ),
                "not_helpful_votes": metrics.get(
                    "not_helpful_votes",
                    ""
                ),
                "hair_type": get_property(
                    details,
                    "hairtype"
                ),
                "incentivized": detect_incentivized_review(
                    review_text
                ),
            })

            if (
                total_results
                and review_progress_bar is not None
                and review_progress_text is not None
            ):
                progress = min(
                    len(all_reviews) / total_results,
                    1.0
                )

                review_progress_bar.progress(progress)

                review_progress_text.write(
                    f"Downloaded {len(all_reviews):,} "
                    f"of {total_results:,} reviews..."
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

    df = pd.DataFrame(all_reviews)
    df.attrs["official_recommendation_rate"] = official_recommendation_rate
    return df

def create_excel_file(df):
    output = BytesIO()
    df = df.copy()

    if "rating" in df.columns:
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")

    total_reviews = len(df)
    avg_rating = round(df["rating"].mean(), 2) if "rating" in df.columns else ""

    summary_df = pd.DataFrame({
        "Metric": [
            "Total Reviews",
            "Average Rating",
            "5 Star Reviews",
            "4 Star Reviews",
            "3 Star Reviews",
            "2 Star Reviews",
            "1 Star Reviews"
        ],
        "Value": [
            total_reviews,
            avg_rating,
            int((df["rating"] == 5).sum()) if "rating" in df.columns else 0,
            int((df["rating"] == 4).sum()) if "rating" in df.columns else 0,
            int((df["rating"] == 3).sum()) if "rating" in df.columns else 0,
            int((df["rating"] == 2).sum()) if "rating" in df.columns else 0,
            int((df["rating"] == 1).sum()) if "rating" in df.columns else 0
        ]
    })

    if "rating" in df.columns:
        rating_breakdown = (
            df["rating"]
            .value_counts()
            .sort_index(ascending=False)
            .reset_index()
        )
        rating_breakdown.columns = ["Rating", "Review Count"]
        rating_breakdown["Percentage"] = rating_breakdown["Review Count"] / total_reviews
    else:
        rating_breakdown = pd.DataFrame(columns=["Rating", "Review Count", "Percentage"])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="Summary")
        df.to_excel(writer, index=False, sheet_name="All Reviews")
        rating_breakdown.to_excel(writer, index=False, sheet_name="Rating Breakdown")

        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions

            for column_cells in worksheet.columns:
                max_length = 0
                column_letter = column_cells[0].column_letter

                for cell in column_cells:
                    if cell.value is not None:
                        max_length = max(max_length, len(str(cell.value)))

                    cell.alignment = cell.alignment.copy(
                        wrap_text=True,
                        vertical="top"
                    )

                worksheet.column_dimensions[column_letter].width = min(max_length + 2, 70)

    output.seek(0)
    return output

def scrape_product(link, delay_seconds, review_progress_bar=None, review_progress_text=None):
    possible_ids = extract_possible_ids(link)

    if review_progress_text is not None:
        review_progress_text.write(f"Trying product IDs: {', '.join(possible_ids)}")

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



