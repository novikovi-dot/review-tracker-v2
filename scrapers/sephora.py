import re
import time
import requests
import pandas as pd


def extract_sephora_product_id(url):
    match = re.search(r"P\d+", url)
    if match:
        return match.group(0)
    return None


def scrape_sephora_product(
    url,
    delay_seconds,
    review_progress_bar=None,
    review_progress_text=None,
    api_key=None
):
    if not api_key:
        raise ValueError("Missing Sephora API key.")

    product_id = extract_sephora_product_id(url)

    if not product_id:
        raise ValueError("Could not find Sephora product ID in link.")

    all_reviews = []
    page = 1
    limit = 100

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "real-time-sephora-api.p.rapidapi.com"
    }

    while True:
        if review_progress_text:
            review_progress_text.write(f"Scraping Sephora reviews page {page}...")

        endpoint = "https://real-time-sephora-api.p.rapidapi.com/product-reviews"

        params = {
            "product_id": product_id,
            "page": page,
            "limit": limit
        }

        response = requests.get(endpoint, headers=headers, params=params, timeout=30)

        if response.status_code != 200:
            raise ValueError(f"Sephora request failed: {response.status_code} - {response.text[:300]}")

        data = response.json()

        reviews = (
            data.get("data", {}).get("reviews")
            or data.get("reviews")
            or []
        )

        if not reviews:
            break

        for review in reviews:
            all_reviews.append({
                "source": "Sephora",
                "product_url": url,
                "product_id": product_id,
                "review_id": review.get("review_id") or review.get("id"),
                "rating": review.get("rating"),
                "title": review.get("title"),
                "review_text": review.get("review_text") or review.get("text") or review.get("review"),
                "reviewer": review.get("nickname") or review.get("author"),
                "review_date": review.get("submission_time") or review.get("date"),
                "verified_purchase": review.get("is_verified_buyer"),
                "recommended": review.get("is_recommended"),
                "skin_type": review.get("skin_type"),
                "skin_concerns": review.get("skin_concerns")
            })

        if review_progress_bar:
            review_progress_bar.progress(min(page / 20, 1.0))

        page += 1
        time.sleep(delay_seconds)

    df = pd.DataFrame(all_reviews)

    if review_progress_text:
        review_progress_text.write(f"Found {len(df)} Sephora reviews.")

    return df
