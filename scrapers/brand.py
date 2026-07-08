import re
import time
import requests
import pandas as pd


YOTPO_STORE_ID = "eEgpPzBZusAXrXgLzWNhAJ6yM7P3XEnyRrdRAovz"

from bs4 import BeautifulSoup

def extract_yotpo_product_id(url):
    # If user pasted the Yotpo API URL directly
    match = re.search(r"/product/(\d+)/reviews", url)
    if match:
        return match.group(1)

    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )

    if response.status_code != 200:
        raise ValueError("Couldn't open product page.")

    html = response.text

    patterns = [
        r'"rid"\s*:\s*(\d+)',
        r'\\"rid\\"\s*:\s*(\d+)',
        r'"rid"\s*:\s*"(\d+)"',
        r'\\"rid\\"\s*:\s*\\"(\d+)\\"'
    ]

    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)

    raise ValueError("Couldn't locate Yotpo product ID.")


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
            "sort": "images,date,rating,badge"
        }

        response = requests.get(endpoint, params=params, timeout=30)

        if response.status_code != 200:
            raise ValueError(f"Brand Website request failed: {response.status_code}")

        data = response.json()

        products = data.get("products", [])
        product_name = products[0].get("name") if products else None

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
                "incentivized": review.get("isIncentivized"),
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
