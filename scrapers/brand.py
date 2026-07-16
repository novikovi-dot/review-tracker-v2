import re
import time
import requests
import pandas as pd


YOTPO_STORE_ID = "eEgpPzBZusAXrXgLzWNhAJ6yM7P3XEnyRrdRAovz"

from bs4 import BeautifulSoup

def normalize_incentivized(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()

    if normalized in {
        "true",
        "yes",
        "1",
        "incentivized",
        "incentivized review"
    }:
        return True

    if normalized in {
        "false",
        "no",
        "0",
        "not incentivized",
        "non-incentivized"
    }:
        return False

    return None

def extract_yotpo_product_id(url):
    # Allow a direct Yotpo API URL.
    match = re.search(r"/product/(\d+)/reviews", url)

    if match:
        return match.group(1)

    clean_url = url.split("?")[0].rstrip("/")
    product_json_url = clean_url + ".js"

    response = requests.get(
        product_json_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        },
        timeout=30
    )

    if response.status_code != 200:
        raise ValueError(
            "Could not load the Shopify product data."
        )

    try:
        product_data = response.json()
    except ValueError as error:
        raise ValueError(
            "The product page did not return valid product data."
        ) from error

    product_id = product_data.get("id")

    if not product_id:
        raise ValueError(
            "Could not locate the Shopify product ID."
        )

    return str(product_id)

def scrape_brand_product(
    url,
    delay_seconds=0.25,
    review_progress_bar=None,
    review_progress_text=None
):
    product_id = extract_yotpo_product_id(url)

    if not product_id:
        raise ValueError("Could not find Yotpo product ID in URL.")

    all_reviews = []
    page = 1
    per_page = 100

    while True:
        if review_progress_text:
            review_progress_text.write(f"Scraping Brand Website reviews page {page}...")

        endpoint = (
            f"https://api-cdn.yotpo.com/v3/storefront/store/"
            f"{YOTPO_STORE_ID}/product/{product_id}/reviews"
        )

        params = {
            "page": page,
            "perPage": per_page,
            "sort": "date"
        }

        response = requests.get(endpoint, params=params, timeout=30)

        if response.status_code != 200:
            raise ValueError(f"Brand Website request failed: {response.status_code}")

        data = response.json()

        products = data.get("products", [])
        product_name = products[0].get("name") if products else None

        if page == 1 and not product_name:
            raise ValueError(
                "Yotpo did not return product information "
                "for this product ID."
            )

        reviews = data.get("reviews", [])

        if not reviews:
            break

        for review in reviews:
            custom_fields = review.get("customFields", {}) or {}

            recommend = None
            for field in custom_fields.values():
                if field.get("title") == "Recommend":
                    recommend = field.get("value")

            topics = review.get("topics", {}) or {}
            topic_names = ", ".join(topics.keys())

            all_reviews.append({
                "source": "Brand Website",
                "brand": "Ole Henriksen",
                "product_name": product_name,
                "product_url": url,
                "product_id": product_id,
                "review_id": review.get("id"),
                "rating": review.get("score"),
                "title": review.get("title"),
                "review_text": review.get("content"),
                "reviewer": None,
                "review_date": review.get("createdAt"),
                "verified_purchase": review.get("verifiedBuyer"),
                "recommended": recommend,
                "incentivized": normalize_incentivized(review.get("isIncentivized")),
                "sentiment": review.get("sentiment"),
                "helpfulness": review.get("votesUp"),
                "not_helpful": review.get("votesDown"),
                "topics": topic_names
            })

        pagination = data.get("pagination", {})
        total_reviews = pagination.get("total")

        if total_reviews and len(all_reviews) >= total_reviews:
            break

        page += 1
        time.sleep(delay_seconds)

        if review_progress_bar and total_reviews:
            review_progress_bar.progress(min(len(all_reviews) / total_reviews, 1.0))

    df = pd.DataFrame(all_reviews)

    if review_progress_text:
        review_progress_text.write(f"Finished Brand Website. Found {len(df)} total reviews.")

    return df
