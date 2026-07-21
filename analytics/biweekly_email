from collections import Counter
from datetime import date, timedelta

import pandas as pd

from database.db import (
    load_new_reviews_for_report,
    load_snapshots
)
from products import PRODUCTS


REPORT_LENGTH_DAYS = 14


# These values must match the source names stored in Supabase.
SOURCE_MAP = {
    "Ulta": "Ulta",
    "Sephora": "Sephora",
    "Brand": "Brand",
    "Brand Website": "Brand",
    "Brand Site": "Brand",
    "OH.com": "Brand"
}


THEME_KEYWORDS = {
    "Hydration": [
        "hydrate",
        "hydrating",
        "hydration",
        "moisture",
        "moisturizing",
        "moisturizer",
        "dryness",
        "dry skin"
    ],
    "Brightening and Glow": [
        "bright",
        "brightening",
        "glow",
        "glowing",
        "radiant",
        "radiance"
    ],
    "Texture and Feel": [
        "texture",
        "sticky",
        "greasy",
        "lightweight",
        "heavy",
        "smooth",
        "soft",
        "absorbs",
        "absorb"
    ],
    "Scent": [
        "scent",
        "smell",
        "fragrance",
        "fragrant"
    ],
    "Irritation or Breakouts": [
        "irritation",
        "irritated",
        "burning",
        "burned",
        "stinging",
        "breakout",
        "breakouts",
        "acne",
        "rash",
        "redness"
    ],
    "Makeup Compatibility": [
        "under makeup",
        "makeup",
        "pilling",
        "pills",
        "foundation",
        "concealer"
    ],
    "Long-Term Results": [
        "results",
        "difference",
        "improvement",
        "improved",
        "weeks",
        "months",
        "long term"
    ],
    "Packaging": [
        "packaging",
        "package",
        "bottle",
        "container",
        "pump",
        "cap",
        "applicator"
    ],
    "Value and Price": [
        "price",
        "expensive",
        "cost",
        "worth",
        "value",
        "overpriced"
    ],
    "Application and Usage": [
        "apply",
        "application",
        "easy to use",
        "difficult to use",
        "routine"
    ]
}


def get_reporting_period(run_date=None):
    """
    Return the previous 14 completed calendar days.

    Example:
    If the report runs July 21, the period is July 7–20.
    """
    if run_date is None:
        run_date = date.today()

    end_date = run_date - timedelta(days=1)

    start_date = end_date - timedelta(
        days=REPORT_LENGTH_DAYS - 1
    )

    return start_date, end_date


def is_valid_product_url(value):
    if value is None:
        return False

    normalized = str(value).strip().lower()

    return normalized not in {
        "",
        "n/a",
        "na",
        "none",
        "null"
    }


def prepare_snapshots(snapshots):
    if snapshots is None or snapshots.empty:
        return pd.DataFrame()

    working_df = snapshots.copy()

    working_df["parsed_scrape_date"] = pd.to_datetime(
        working_df["scrape_date"],
        errors="coerce"
    )

    working_df = (
        working_df
        .dropna(subset=["parsed_scrape_date"])
        .sort_values("parsed_scrape_date")
        .reset_index(drop=True)
    )

    return working_df


def get_snapshot_as_of(
    snapshots,
    target_date
):
    """
    Return the latest available snapshot on or before target_date.
    """
    working_df = prepare_snapshots(snapshots)

    if working_df.empty:
        return None

    target_timestamp = pd.Timestamp(target_date)

    eligible_snapshots = working_df[
        working_df["parsed_scrape_date"]
        <= target_timestamp
    ]

    if eligible_snapshots.empty:
        return None

    return eligible_snapshots.iloc[-1]


def clean_numeric(value):
    numeric_value = pd.to_numeric(
        value,
        errors="coerce"
    )

    if pd.isna(numeric_value):
        return None

    return float(numeric_value)


def calculate_snapshot_rating_change(
    snapshots,
    start_date,
    end_date
):
    baseline_snapshot = get_snapshot_as_of(
        snapshots=snapshots,
        target_date=start_date
    )

    current_snapshot = get_snapshot_as_of(
        snapshots=snapshots,
        target_date=end_date
    )

    if (
        baseline_snapshot is None
        or current_snapshot is None
    ):
        return None

    baseline_date = (
        baseline_snapshot["parsed_scrape_date"]
        .date()
    )

    current_date = (
        current_snapshot["parsed_scrape_date"]
        .date()
    )

    if baseline_date == current_date:
        return None

    baseline_rating = clean_numeric(
        baseline_snapshot.get(
            "average_rating"
        )
    )

    current_rating = clean_numeric(
        current_snapshot.get(
            "average_rating"
        )
    )

    if (
        baseline_rating is None
        or current_rating is None
    ):
        return None

    return {
        "baseline_date": baseline_date,
        "current_date": current_date,
        "baseline_rating": baseline_rating,
        "current_rating": current_rating,
        "rating_change": (
            current_rating
            - baseline_rating
        ),
        "current_total_reviews": clean_numeric(
            current_snapshot.get(
                "total_reviews"
            )
        )
    }


def get_review_text(row):
    title = row.get("review_title")
    text = row.get("review_text")

    parts = []

    if title is not None:
        parts.append(str(title))

    if text is not None:
        parts.append(str(text))

    return " ".join(parts).lower()


def find_themes(reviews_df):
    theme_counts = Counter()

    if reviews_df is None or reviews_df.empty:
        return theme_counts

    for _, row in reviews_df.iterrows():
        review_text = get_review_text(row)

        matched_themes = set()

        for theme_name, keywords in THEME_KEYWORDS.items():
            if any(
                keyword in review_text
                for keyword in keywords
            ):
                matched_themes.add(theme_name)

        for theme_name in matched_themes:
            theme_counts[theme_name] += 1

    return theme_counts


def format_theme_summary(
    reviews_df,
    maximum_themes=3
):
    theme_counts = find_themes(reviews_df)

    if not theme_counts:
        return "No recurring themes detected"

    top_themes = theme_counts.most_common(
        maximum_themes
    )

    return ", ".join(
        f"{theme} ({count})"
        for theme, count in top_themes
    )


def split_reviews_by_rating(reviews_df):
    if reviews_df is None or reviews_df.empty:
        empty_df = pd.DataFrame()

        return empty_df, empty_df, empty_df

    working_df = reviews_df.copy()

    working_df["numeric_rating"] = pd.to_numeric(
        working_df["rating"],
        errors="coerce"
    )

    positive_reviews = working_df[
        working_df["numeric_rating"] >= 4
    ]

    mixed_reviews = working_df[
        working_df["numeric_rating"] == 3
    ]

    negative_reviews = working_df[
        working_df["numeric_rating"] <= 2
    ]

    return (
        positive_reviews,
        mixed_reviews,
        negative_reviews
    )


def calculate_new_review_average(
    reviews_df
):
    if reviews_df is None or reviews_df.empty:
        return None

    ratings = pd.to_numeric(
        reviews_df["rating"],
        errors="coerce"
    ).dropna()

    if ratings.empty:
        return None

    return float(ratings.mean())


def format_rating(value):
    if value is None:
        return "N/A"

    return f"{value:.3f}"


def format_rating_change(value):
    if value is None:
        return "N/A"

    return f"{value:+.3f}"


def build_platform_section(
    product_name,
    platform_name,
    source,
    start_date,
    end_date
):
    snapshots = load_snapshots(
        product_name=product_name,
        source=source
    )

    snapshot_change = (
        calculate_snapshot_rating_change(
            snapshots=snapshots,
            start_date=start_date,
            end_date=end_date
        )
    )

    new_reviews = load_new_reviews_for_report(
        product_name=product_name,
        source=source,
        start_date=start_date,
        end_date=end_date
    )

    (
        positive_reviews,
        mixed_reviews,
        negative_reviews
    ) = split_reviews_by_rating(new_reviews)

    new_review_average = (
        calculate_new_review_average(
            new_reviews
        )
    )

    lines = [
        f"  {platform_name}",
        f"  New reviews: {len(new_reviews)}",
        (
            "  Average rating of new reviews: "
            f"{format_rating(new_review_average)}"
        )
    ]

    if snapshot_change is None:
        lines.append(
            "  Overall rating change: "
            "Not enough snapshot history"
        )
    else:
        lines.extend([
            (
                "  Overall rating: "
                f"{format_rating(snapshot_change['baseline_rating'])}"
                " → "
                f"{format_rating(snapshot_change['current_rating'])}"
            ),
            (
                "  Overall rating change: "
                f"{format_rating_change(snapshot_change['rating_change'])}"
            ),
            (
                "  Snapshot comparison: "
                f"{snapshot_change['baseline_date'].isoformat()}"
                " → "
                f"{snapshot_change['current_date'].isoformat()}"
            )
        ])

    if new_reviews.empty:
        lines.append(
            "  Themes: No new reviews during this period"
        )
    else:
        lines.extend([
            (
                "  Positive themes: "
                f"{format_theme_summary(positive_reviews)}"
            ),
            (
                "  Mixed themes: "
                f"{format_theme_summary(mixed_reviews)}"
            ),
            (
                "  Negative themes: "
                f"{format_theme_summary(negative_reviews)}"
            )
        ])

    return "\n".join(lines)


def build_biweekly_report(
    run_date=None
):
    start_date, end_date = get_reporting_period(
        run_date=run_date
    )

    report_lines = [
        "Ole Henriksen Biweekly Review Report",
        (
            "Reporting period: "
            f"{start_date.isoformat()}"
            " to "
            f"{end_date.isoformat()}"
        ),
        ""
    ]

    for product_name, platforms in PRODUCTS.items():
        report_lines.append(product_name)

        included_platform = False

        for platform_name, product_url in platforms.items():
            if not is_valid_product_url(product_url):
                continue

            included_platform = True

            source = SOURCE_MAP.get(
                platform_name,
                platform_name
            )

            platform_section = build_platform_section(
                product_name=product_name,
                platform_name=platform_name,
                source=source,
                start_date=start_date,
                end_date=end_date
            )

            report_lines.append(
                platform_section
            )

        if not included_platform:
            report_lines.append(
                "  No active platforms"
            )

        report_lines.append("")

    return "\n".join(report_lines)


def main():
    report = build_biweekly_report()

    # Preview only. No email is sent at this stage.
    print(report)


if __name__ == "__main__":
    main()
