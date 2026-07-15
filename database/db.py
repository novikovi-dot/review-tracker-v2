from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client, create_client


def get_supabase_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SERVICE_KEY"]

    return create_client(url, key)


def clean_value(value):
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()

        if value == "":
            return None

        return value

    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, datetime):
        return value.isoformat()

    if hasattr(value, "item"):
        return value.item()

    return value


def normalize_boolean(value):
    if value is None or pd.isna(value):
        return None

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()

    if normalized in {
        "true",
        "yes",
        "1",
        "verified",
        "verifiedpurchaser",
        "verified purchaser"
    }:
        return True

    if normalized in {"false", "no", "0"}:
        return False

    return None


def first_available(row, column_names, default=None):
    for column_name in column_names:
        if column_name in row.index:
            value = row.get(column_name)

            if value is not None and not pd.isna(value):
                return value

    return default


def build_review_record(
    row,
    source,
    product_name,
    product_url
):
    review_id = first_available(
        row,
        ["review_id", "Id", "id"]
    )

    rating = first_available(
        row,
        ["rating", "Rating", "score"]
    )

    review_title = first_available(
        row,
        ["review_title", "title", "Title"]
    )

    review_text = first_available(
        row,
        ["review_text", "ReviewText", "content"]
    )

    reviewer_name = first_available(
        row,
        ["reviewer_name", "reviewer", "UserNickname"]
    )

    review_date = first_available(
        row,
        ["created_date", "review_date", "SubmissionTime", "createdAt"]
    )

    helpful_votes = first_available(
        row,
        ["helpful_votes", "helpfulness", "TotalPositiveFeedbackCount", "votesUp"]
    )

    not_helpful_votes = first_available(
        row,
        [
            "not_helpful_votes",
            "not_helpful",
            "TotalNegativeFeedbackCount",
            "votesDown"
        ]
    )

    return {
        "product_name": product_name,
        "product_url": product_url,
        "source": source,
        "review_id": str(review_id),
        "rating": clean_value(rating),
        "review_title": clean_value(review_title),
        "review_text": clean_value(review_text),
        "reviewer_name": clean_value(reviewer_name),
        "location": clean_value(first_available(row, ["location"])),
        "review_date": clean_value(review_date),
        "helpful_votes": clean_value(helpful_votes),
        "not_helpful_votes": clean_value(not_helpful_votes),
        "hair_type": clean_value(first_available(row, ["hair_type"])),
        "skin_type": clean_value(first_available(row, ["skin_type"])),
        "age_range": clean_value(first_available(row, ["age_range"])),
        "recommended": normalize_boolean(
            first_available(row, ["recommended"])
        ),
        "verified_purchase": normalize_boolean(
            first_available(row, ["verified_purchase"])
        ),
        "incentivized": normalize_boolean(
            first_available(row, ["incentivized"])
        ),
        "sentiment": clean_value(first_available(row, ["sentiment"])),
        "topics": clean_value(first_available(row, ["topics"])),
        "last_seen_at": datetime.utcnow().isoformat()
    }

def save_reviews(df, source, product_name, product_url):
    if df is None or df.empty:
        return 0, pd.DataFrame()

    client = get_supabase_client()
    records = []

    for _, row in df.iterrows():
        record = build_review_record(
            row=row,
            source=source,
            product_name=product_name,
            product_url=product_url
        )

        if record["review_id"] in {"None", "", "nan"}:
            continue

        records.append(record)

    if not records:
        return 0, pd.DataFrame()

    existing_ids = get_existing_review_ids(
        product_name=product_name,
        source=source
    )

    new_records = [
        record
        for record in records
        if record["review_id"] not in existing_ids
    ]

    batch_size = 100

    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]

        client.table("reviews").upsert(
            batch,
            on_conflict="source,product_name,review_id"
        ).execute()

    new_reviews_df = pd.DataFrame(new_records)

    return len(new_records), new_reviews_df


def get_existing_review_ids(product_name, source):
    client = get_supabase_client()

    existing_ids = set()
    start = 0
    requested_page_size = 1000

    while True:
        response = (
            client.table("reviews")
            .select("id,review_id")
            .eq("product_name", product_name)
            .eq("source", source)
            .order("id")
            .range(start, start + requested_page_size - 1)
            .execute()
        )

        rows = response.data or []

        if not rows:
            break

        for row in rows:
            review_id = row.get("review_id")

            if review_id is not None:
                existing_ids.add(str(review_id))

        # Move forward by the number Supabase actually returned,
        # rather than assuming it returned 1,000.
        start += len(rows)

    return existing_ids

def calculate_snapshot(df, source, product_name, product_url):
    ratings = pd.to_numeric(
        df.get("rating", pd.Series(dtype=float)),
        errors="coerce"
    )

    recommendation_rate = None

    if "recommended" in df.columns:
        recommendations = df["recommended"].apply(normalize_boolean)
        valid_recommendations = recommendations.dropna()

        if not valid_recommendations.empty:
            recommendation_rate = round(
                valid_recommendations.mean() * 100,
                2
            )

    verified_purchase_rate = None

    if "verified_purchase" in df.columns:
        verified = df["verified_purchase"].apply(normalize_boolean)
        valid_verified = verified.dropna()

        if not valid_verified.empty:
            verified_purchase_rate = round(
                valid_verified.mean() * 100,
                2
            )

    return {
        "product_name": product_name,
        "source": source,
        "scrape_date": date.today().isoformat(),
        "product_url": product_url,
        "total_reviews": int(len(df)),
        "average_rating": (
            round(float(ratings.mean()), 3)
            if ratings.notna().any()
            else None
        ),
        "five_star_reviews": int((ratings == 5).sum()),
        "four_star_reviews": int((ratings == 4).sum()),
        "three_star_reviews": int((ratings == 3).sum()),
        "two_star_reviews": int((ratings == 2).sum()),
        "one_star_reviews": int((ratings == 1).sum()),
        "recommendation_rate": recommendation_rate,
        "verified_purchase_rate": verified_purchase_rate
    }


def save_snapshot(df, source, product_name, product_url):
    if df is None or df.empty:
        return

    client = get_supabase_client()

    snapshot = calculate_snapshot(
        df=df,
        source=source,
        product_name=product_name,
        product_url=product_url
    )

    client.table("snapshots").upsert(
        snapshot,
        on_conflict="product_name,source,scrape_date"
    ).execute()


def load_new_reviews(product_name, source, since_date):
    client = get_supabase_client()

    response = (
        client.table("reviews")
        .select("*")
        .eq("product_name", product_name)
        .eq("source", source)
        .gte("first_seen_at", since_date)
        .order("first_seen_at")
        .execute()
    )

    return pd.DataFrame(response.data or [])


def load_snapshots(product_name, source=None):
    client = get_supabase_client()

    query = (
        client.table("snapshots")
        .select("*")
        .eq("product_name", product_name)
        .order("scrape_date")
    )

    if source:
        query = query.eq("source", source)

    response = query.execute()

    return pd.DataFrame(response.data or [])

def get_snapshot_changes(product_name, source):
    snapshots = load_snapshots(
        product_name=product_name,
        source=source
    )

    if snapshots.empty or len(snapshots) < 2:
        return None

    snapshots["scrape_date"] = pd.to_datetime(
        snapshots["scrape_date"],
        errors="coerce"
    )

    snapshots = (
        snapshots
        .dropna(subset=["scrape_date"])
        .sort_values("scrape_date")
        .reset_index(drop=True)
    )

    if len(snapshots) < 2:
        return None

    previous = snapshots.iloc[-2]
    current = snapshots.iloc[-1]

    previous_rating = pd.to_numeric(
        previous.get("average_rating"),
        errors="coerce"
    )

    current_rating = pd.to_numeric(
        current.get("average_rating"),
        errors="coerce"
    )

    if (
        pd.isna(previous_rating)
        or pd.isna(current_rating)
    ):
        rating_change = None
    else:
        rating_change = round(
            float(current_rating - previous_rating),
            3
        )

    return {
        "previous_scrape_date": (
            previous["scrape_date"]
            .date()
            .isoformat()
        ),
        "current_scrape_date": (
            current["scrape_date"]
            .date()
            .isoformat()
        ),
        "previous_average_rating": (
            float(previous_rating)
            if pd.notna(previous_rating)
            else None
        ),
        "current_average_rating": (
            float(current_rating)
            if pd.notna(current_rating)
            else None
        ),
        "rating_change": rating_change
    }
