import pandas as pd
import requests
import re
import time
import urllib3
from io import BytesIO
from urllib.parse import urljoin
import hashlib
from html import unescape

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

    # Extract the numeric SKU first.
    sku_match = re.search(
        r"(?:\?|&)sku=(\d+)",
        link,
        flags=re.IGNORECASE
    )

    if sku_match:
        ids.append(sku_match.group(1))

    # Then try the product-page IDs.
    other_patterns = [
        r"pimprod\d+",
        r"mkt\d+",
        r"[a-zA-Z]*impprod\d+"
    ]

    for pattern in other_patterns:
        matches = re.findall(
            pattern,
            link,
            flags=re.IGNORECASE
        )

        ids.extend(matches)

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

def extract_review_date(review):
    preferred_keys = (
        "created_date",
        "createdDate",
        "review_date",
        "reviewDate",
        "submission_time",
        "submissionTime",
        "submission_date",
        "submissionDate",
        "date_created",
        "dateCreated",
        "created_at",
        "createdAt",
        "published_at",
        "publishedAt",
        "display_date",
        "displayDate",
        "date"
    )

    def search_nested(value):
        if isinstance(value, dict):
            for key in preferred_keys:
                candidate = value.get(key)

                if candidate is None:
                    continue

                if (
                    isinstance(candidate, str)
                    and candidate.strip() == ""
                ):
                    continue

                return candidate

            for nested_value in value.values():
                result = search_nested(nested_value)

                if result is not None:
                    return result

        elif isinstance(value, list):
            for item in value:
                result = search_nested(item)

                if result is not None:
                    return result

        return None

    return search_nested(review)

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

def scrape_reviews(
    product_id,
    delay_seconds,
    review_progress_bar=None,
    review_progress_text=None
):
    all_reviews = []

    official_recommendation_rate = ""
    official_average_rating = None
    official_total_reviews = None

    base_url = "https://display.powerreviews.com"

    next_url = (
        f"{base_url}/m/6406/l/en_US/"
        f"product/{product_id}/reviews"
    )

    request_params = {
        "apikey": API_KEY,
        "_noconfig": "true",
        "sort": "Newest",
        "image_only": "false",
        "page_locale": "en_US"
    }

    seen_page_urls = set()
    page_number = 0

    while next_url:
        page_number += 1

        request_signature = (
            next_url,
            tuple(sorted(request_params.items()))
        )

        if request_signature in seen_page_urls:
            raise RuntimeError(
                "Ulta pagination repeated the same page. "
                "The scrape was stopped to prevent duplicate data."
            )

        seen_page_urls.add(request_signature)

        response = make_request(
            next_url,
            request_params
        )

        if response is None:
            raise RuntimeError(
                f"Ulta page {page_number} could not be "
                "downloaded after multiple attempts. "
                "No partial report was saved."
            )

        try:
            data = response.json()
        except ValueError as error:
            raise RuntimeError(
                f"Ulta page {page_number} returned "
                "invalid JSON."
            ) from error

        results = data.get("results", []) or []

        if page_number == 1:
            print("\n========== ULTA API DIAGNOSTIC ==========")
            print(f"Requested product ID: {product_id}")
            print(f"Top-level response keys: {list(data.keys())}")
            print(f"Paging data: {data.get('paging', {})}")
            print(f"Number of result groups: {len(results)}")
            
            for index, result in enumerate(results):
                rollup = result.get("rollup", {}) or {}
            
                print(f"\nResult group {index + 1}")
                print(f"Result keys: {list(result.keys())}")
                print(f"Page ID: {result.get('page_id')}")
                print(f"Page ID alternate: {result.get('pageId')}")
                print(f"Product ID: {result.get('product_id')}")
                print(f"Product ID alternate: {result.get('productId')}")
                print(f"Rollup review count: {rollup.get('review_count')}")
                print(f"Reviews on first page: {len(result.get('reviews', []) or [])}")
            
            print("=========================================\n")
        
        if not results:
            break

        paging = data.get("paging", {}) or {}

        reported_total = paging.get(
            "total_results"
        )

        if reported_total not in [None, ""]:
            try:
                official_total_reviews = int(
                    reported_total
                )
            except (TypeError, ValueError):
                pass

        page_review_count = 0

        # Important:
        # Process every result group, not only results[0].
        for result in results:
            rollup = result.get(
                "rollup",
                {}
            ) or {}

            recommended_ratio = rollup.get(
                "recommended_ratio"
            )

            if recommended_ratio not in [None, ""]:
                try:
                    official_recommendation_rate = (
                        f"{round(float(recommended_ratio) * 100)}%"
                    )
                except (TypeError, ValueError):
                    pass

            average_rating_value = rollup.get(
                "average_rating"
            )

            if average_rating_value in [None, ""]:
                average_rating_value = rollup.get(
                    "averageRating"
                )

            if average_rating_value not in [None, ""]:
                try:
                    official_average_rating = float(
                        average_rating_value
                    )
                except (TypeError, ValueError):
                    pass

            rollup_review_count = rollup.get(
                "review_count"
            )

            if (
                official_total_reviews is None
                and rollup_review_count not in [None, ""]
            ):
                try:
                    official_total_reviews = int(
                        rollup_review_count
                    )
                except (TypeError, ValueError):
                    pass

            reviews = result.get(
                "reviews",
                []
            ) or []

            for review in reviews:
                details = review.get(
                    "details",
                    {}
                ) or {}

                metrics = review.get(
                    "metrics",
                    {}
                ) or {}

                review_text = (
                    details.get(
                        "comments",
                        ""
                    )
                    or ""
                )

                review_title = (
                    details.get(
                        "headline",
                        ""
                    )
                    or ""
                )

                reviewer_name = (
                    details.get(
                        "nickname",
                        ""
                    )
                    or ""
                )

                review_date = extract_review_date(
                    review
                )

                rating = metrics.get(
                    "rating",
                    ""
                )

                review_id = (
                    review.get("review_id")
                    or review.get("reviewId")
                    or review.get("id")
                )

                # Do not discard a review solely because
                # Ulta omitted its normal review ID.
                if review_id in [None, ""]:
                    fingerprint_text = "|".join([
                        str(product_id),
                        str(review_date or ""),
                        str(rating or ""),
                        str(reviewer_name),
                        str(review_title),
                        str(review_text)
                    ])

                    fingerprint = hashlib.sha256(
                        fingerprint_text.encode(
                            "utf-8"
                        )
                    ).hexdigest()

                    review_id = (
                        f"generated_{fingerprint}"
                    )

                all_reviews.append({
                    "matched_id": product_id,
                    "review_id": str(review_id),
                    "rating": rating,
                    "review_title": review_title,
                    "review_text": review_text,
                    "reviewer_name": reviewer_name,
                    "location": (
                        review.get("location")
                        or details.get(
                            "location",
                            ""
                        )
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
                    "incentivized": (
                        detect_incentivized_review(
                            review_text
                        )
                    )
                })

                page_review_count += 1

        if (
            official_total_reviews
            and review_progress_bar is not None
            and review_progress_text is not None
        ):
            unique_downloaded = len({
                review["review_id"]
                for review in all_reviews
            })

            progress = min(
                unique_downloaded
                / official_total_reviews,
                1.0
            )

            review_progress_bar.progress(
                progress
            )

            review_progress_text.write(
                f"Downloaded "
                f"{unique_downloaded:,} of "
                f"{official_total_reviews:,} "
                "reviews..."
            )

        if page_review_count == 0:
            break

        next_page_url = paging.get(
            "next_page_url"
        )

        if next_page_url:
            next_url = urljoin(
                base_url,
                unescape(
                    str(next_page_url)
                )
            )

            request_params = {
                "apikey": API_KEY,
                "_noconfig": "true"
            }

        else:
            next_url = None

        time.sleep(delay_seconds)

    df = pd.DataFrame(
        all_reviews
    )

    if not df.empty:
        df = df.drop_duplicates(
            subset=["review_id"],
            keep="first"
        ).reset_index(drop=True)

    downloaded_count = len(df)

    df.attrs[
        "official_recommendation_rate"
    ] = official_recommendation_rate

    df.attrs[
        "official_average_rating"
    ] = official_average_rating

    df.attrs[
        "official_total_reviews"
    ] = official_total_reviews

    df.attrs[
        "downloaded_review_count"
    ] = downloaded_count

    if (
        official_total_reviews is not None
        and downloaded_count < official_total_reviews
    ):
        raise RuntimeError(
            "Ulta scrape was incomplete: "
            f"downloaded {downloaded_count:,} unique reviews "
            f"but Ulta reported {official_total_reviews:,}. "
            "The incomplete dataset was not returned or saved."
        )

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

def scrape_product(
    link,
    delay_seconds,
    review_progress_bar=None,
    review_progress_text=None
):
    possible_ids = extract_possible_ids(link)

    if review_progress_text is not None:
        review_progress_text.write(
            "Trying product IDs: "
            + ", ".join(possible_ids)
        )

    if not possible_ids:
        return None, None

    errors = []

    for product_id in possible_ids:
        if review_progress_text is not None:
            review_progress_text.write(
                f"Trying Ulta ID: {product_id}"
            )

        try:
            df = scrape_reviews(
                product_id,
                delay_seconds,
                review_progress_bar,
                review_progress_text
            )

        except RuntimeError as error:
            errors.append(
                f"{product_id}: {str(error)}"
            )

            if review_progress_text is not None:
                review_progress_text.write(
                    f"ID {product_id} was incomplete. "
                    "Trying the next ID..."
                )

            continue

        if df is not None and not df.empty:
            return df, product_id

    if errors:
        raise RuntimeError(
            "No Ulta ID produced a complete scrape. "
            + " | ".join(errors)
        )

    return None, None


