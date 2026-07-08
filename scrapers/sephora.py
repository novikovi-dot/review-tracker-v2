import re
import time
import requests
import pandas as pd
from io import BytesIO


SEPHORA_PASSKEY = "calXm2DyQVjcCy9agq85vmTJv5ELuuBCF2sdg4BnJzJus"


def extract_sephora_product_id(url):
    match = re.search(r"P\d+", url)
    if match:
        return match.group(0)
    return None


def scrape_sephora_product(
    url,
    delay_seconds=0.25,
    review_progress_bar=None,
    review_progress_text=None
):
    product_id = extract_sephora_product_id(url)

    if not product_id:
        raise ValueError("Could not find Sephora product ID in URL.")

    all_reviews = []
    limit = 100
    offset = 0

    while True:
        if review_progress_text:
            review_progress_text.write(f"Scraping Sephora reviews {offset + 1} to {offset + limit}...")

        params = {
            "Filter": [
                "contentlocale:en*",
                f"ProductId:{product_id}"
            ],
            "Sort": "SubmissionTime:desc",
            "Limit": limit,
            "Offset": offset,
            "Include": "Products,Comments",
            "Stats": "Reviews",
            "passkey": SEPHORA_PASSKEY,
            "apiversion": "5.4",
            "Locale": "en_US"
        }

        response = requests.get(
            "https://api.bazaarvoice.com/data/reviews.json",
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            raise ValueError(f"Sephora request failed: {response.status_code}")

        data = response.json()
        reviews = data.get("Results", [])

        if not reviews:
            break

        product_info = {}
        products = data.get("Includes", {}).get("Products", {})

        if products:
            first_product = list(products.values())[0]
            product_info = {
                "brand": first_product.get("Brand", {}).get("Name"),
                "product_name": first_product.get("Name"),
                "product_id": product_id,
                "product_url": url
            }

        for review in reviews:
            context = review.get("ContextDataValues", {}) or {}

            all_reviews.append({
                "source": "Sephora",
                "brand": product_info.get("brand"),
                "product_name": product_info.get("product_name"),
                "product_url": url,
                "product_id": product_id,
                "review_id": review.get("Id"),
                "rating": review.get("Rating"),
                "title": review.get("Title"),
                "review_text": review.get("ReviewText"),
                "reviewer": review.get("UserNickname"),
                "review_date": review.get("SubmissionTime"),
                "recommended": review.get("IsRecommended"),
                "verified_purchase": review.get("Badges", {}).get("verifiedPurchaser", {}).get("ContentType"),
                "skin_type": context.get("skinType", {}).get("Value"),
                "skin_concerns": context.get("skinConcerns", {}).get("Value"),
                "age_range": context.get("ageRange", {}).get("Value"),
                "incentivized": context.get("IncentivizedReview", {}).get("Value"),
                "helpfulness": review.get("TotalPositiveFeedbackCount"),
                "not_helpful": review.get("TotalNegativeFeedbackCount")
            })

        offset += limit

        if review_progress_bar:
            review_progress_bar.progress(min(offset / 1000, 1.0))

        time.sleep(delay_seconds)

    df = pd.DataFrame(all_reviews)

    if review_progress_text:
        review_progress_text.write(f"Found {len(df)} Sephora reviews.")

    return df
