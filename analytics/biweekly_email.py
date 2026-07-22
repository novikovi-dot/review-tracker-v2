from collections import Counter
from datetime import date, timedelta
from html import escape

import pandas as pd

from database.db import (
    load_all_reviews,
    load_reviews_by_date_range,
    get_period_snapshot_change
)

from analytics.reporting import (
    calculate_period_rating_change
)

from products import PRODUCTS

REPORT_LENGTH_DAYS = 14

SOURCE_CANDIDATES = {
    "Ulta": [
        "Ulta"
    ],
    "Sephora": [
        "Sephora"
    ],
    "Brand": [
        "Brand",
        "Brand Website",
        "OH.com"
    ],
    "Brand Website": [
        "Brand Website",
        "Brand",
        "OH.com"
    ],
    "Brand Site": [
        "Brand Site",
        "Brand",
        "Brand Website",
        "OH.com"
    ],
    "OH.com": [
        "OH.com",
        "Brand",
        "Brand Website"
    ]
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

    return f"{value:.2f}"


def format_rating_change(value):
    if value is None:
        return "N/A"

    return f"{value:+.2f}"

def load_platform_report_data(
    product_name,
    platform_name,
    start_date,
    end_date
):
    """
    Load reviews using the source name stored in Supabase.

    Period reviews are selected by their publication date.
    All reviews are used only to calculate the cumulative
    rating at the beginning and end of the period.
    """
    source_candidates = SOURCE_CANDIDATES.get(
        platform_name,
        [platform_name]
    )

    fallback_result = (
        source_candidates[0],
        pd.DataFrame(),
        pd.DataFrame()
    )

    for source in source_candidates:
        period_reviews = load_reviews_by_date_range(
            product_name=product_name,
            source=source,
            start_date=start_date,
            end_date=end_date
        )

        all_reviews = load_all_reviews(
            product_name=product_name,
            source=source
        )

        if not all_reviews.empty:
            return (
                source,
                period_reviews,
                all_reviews
            )

        if not period_reviews.empty:
            fallback_result = (
                source,
                period_reviews,
                all_reviews
            )

    return fallback_result


def normalize_incentivized_value(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()

    if normalized in {
        "true",
        "yes",
        "1",
        "incentivized"
    }:
        return True

    if normalized in {
        "false",
        "no",
        "0",
        "non-incentivized",
        "non incentivized"
    }:
        return False

    return None


def calculate_incentive_breakdown(
    reviews_df
):
    result = {
        "incentivized_count": 0,
        "incentivized_average": None,
        "non_incentivized_count": 0,
        "non_incentivized_average": None,
        "unclassified_count": 0
    }

    if reviews_df is None or reviews_df.empty:
        return result

    working_df = reviews_df.copy()

    working_df["numeric_rating"] = pd.to_numeric(
        working_df.get(
            "rating",
            pd.Series(
                index=working_df.index,
                dtype=float
            )
        ),
        errors="coerce"
    )

    incentive_values = working_df.get(
        "incentivized",
        pd.Series(
            index=working_df.index,
            dtype=object
        )
    )

    working_df["incentive_flag"] = (
        incentive_values.apply(
            normalize_incentivized_value
        )
    )

    incentivized_reviews = working_df[
        working_df["incentive_flag"].eq(True)
    ]

    non_incentivized_reviews = working_df[
        working_df["incentive_flag"].eq(False)
    ]

    unclassified_reviews = working_df[
        working_df["incentive_flag"].isna()
    ]

    incentivized_ratings = (
        incentivized_reviews["numeric_rating"]
        .dropna()
    )

    non_incentivized_ratings = (
        non_incentivized_reviews["numeric_rating"]
        .dropna()
    )

    result["incentivized_count"] = int(
        len(incentivized_reviews)
    )

    result["non_incentivized_count"] = int(
        len(non_incentivized_reviews)
    )

    result["unclassified_count"] = int(
        len(unclassified_reviews)
    )

    if not incentivized_ratings.empty:
        result["incentivized_average"] = float(
            incentivized_ratings.mean()
        )

    if not non_incentivized_ratings.empty:
        result["non_incentivized_average"] = float(
            non_incentivized_ratings.mean()
        )

    return result

def build_platform_section(
    product_name,
    platform_name,
    start_date,
    end_date
):
    (
        source_used,
        period_reviews,
        all_reviews
    ) = load_platform_report_data(
        product_name=product_name,
        platform_name=platform_name,
        start_date=start_date,
        end_date=end_date
    )

    period_review_count = int(
        len(period_reviews)
    )

    period_average = calculate_new_review_average(
        period_reviews
    )

    snapshot_comparison = get_period_snapshot_change(
        product_name=product_name,
        source=source_used,
        start_date=start_date,
        end_date=end_date
    )

    review_comparison = calculate_period_rating_change(
        reviews_df=all_reviews,
        start_date=start_date,
        end_date=end_date
    )

    baseline_date = (
        pd.Timestamp(start_date)
        - pd.Timedelta(days=1)
    ).date().isoformat()

    end_rating_date = (
        pd.Timestamp(end_date)
        .date()
        .isoformat()
    )

    baseline_rating_value = None
    end_rating_value = None

    # Use cumulative review history as a fallback when
    # no historical snapshot exists for the required date.
    if review_comparison is not None:
        review_baseline = review_comparison.get(
            "baseline_rating"
        )

        review_current = review_comparison.get(
            "current_rating"
        )

        if review_baseline is not None:
            baseline_rating_value = float(
                review_baseline
            )

        if review_current is not None:
            end_rating_value = float(
                review_current
            )

        baseline_date = str(
            review_comparison.get(
                "previous_period_end",
                baseline_date
            )
        )

    # Prefer official retailer ratings from snapshots
    # whenever an eligible snapshot exists.
    if snapshot_comparison is not None:
        snapshot_baseline = snapshot_comparison.get(
            "baseline_rating"
        )

        snapshot_current = snapshot_comparison.get(
            "current_rating"
        )

        snapshot_baseline_date = (
            snapshot_comparison.get(
                "previous_period_end"
            )
        )

        snapshot_current_date = (
            snapshot_comparison.get(
                "current_period_end"
            )
        )

        if snapshot_baseline is not None:
            baseline_rating_value = float(
                snapshot_baseline
            )

            if snapshot_baseline_date:
                baseline_date = str(
                    snapshot_baseline_date
                )

        if snapshot_current is not None:
            end_rating_value = float(
                snapshot_current
            )

            if snapshot_current_date:
                end_rating_date = str(
                    snapshot_current_date
                )

    start_rating = format_rating(
        baseline_rating_value
    )

    end_rating = format_rating(
        end_rating_value
    )

    if (
        baseline_rating_value is not None
        and end_rating_value is not None
    ):
        rating_change_value = format_rating_change(
            end_rating_value
            - baseline_rating_value
        )
    else:
        rating_change_value = "N/A"

    incentive_breakdown = calculate_incentive_breakdown(
        period_reviews
    )
    incentive_breakdown = calculate_incentive_breakdown(
        period_reviews
    )

    (
        positive_reviews,
        mixed_reviews,
        negative_reviews
    ) = split_reviews_by_rating(
        period_reviews
    )

    bullet_items = [
        (
            "<li>"
            "<strong>Reviews published during period:</strong> "
            f"{period_review_count}"
            "</li>"
        ),
        (
            "<li>"
            "<strong>Average rating of period reviews:</strong> "
            f"{format_rating(period_average)}"
            "</li>"
        ),
        (
            "<li>"
            "<strong>Overall rating at start of period:</strong> "
            f"{start_rating} "
            f"(through {baseline_date})"
            "</li>"
        ),
        (
            "<li>"
            "<strong>Overall rating at end of period:</strong> "
            f"{end_rating} "
            f"(through {end_rating_date})"
            "</li>"
        ),
        (
            "<li>"
            "<strong>Overall rating change:</strong> "
            f"{rating_change_value}"
            "</li>"
        ),
        (
            "<li>"
            "<strong>Incentivized reviews:</strong> "
            f"{incentive_breakdown['incentivized_count']} "
            "reviews; average rating "
            f"{format_rating(
                incentive_breakdown[
                    'incentivized_average'
                ]
            )}"
            "</li>"
        ),
        (
            "<li>"
            "<strong>Non-incentivized reviews:</strong> "
            f"{incentive_breakdown['non_incentivized_count']} "
            "reviews; average rating "
            f"{format_rating(
                incentive_breakdown[
                    'non_incentivized_average'
                ]
            )}"
            "</li>"
        )
    ]

    if incentive_breakdown["unclassified_count"] > 0:
        bullet_items.append(
            (
                "<li>"
                "<strong>Unclassified reviews:</strong> "
                f"{incentive_breakdown['unclassified_count']}"
                "</li>"
            )
        )

    if period_reviews.empty:
        bullet_items.append(
            (
                "<li>"
                "<strong>Review themes:</strong> "
                "No reviews were published during this period"
                "</li>"
            )
        )

    else:
        bullet_items.extend([
            (
                "<li>"
                "<strong>Positive themes:</strong> "
                f"{escape(
                    format_theme_summary(
                        positive_reviews
                    )
                )}"
                "</li>"
            ),
            (
                "<li>"
                "<strong>Mixed themes:</strong> "
                f"{escape(
                    format_theme_summary(
                        mixed_reviews
                    )
                )}"
                "</li>"
            ),
            (
                "<li>"
                "<strong>Negative themes:</strong> "
                f"{escape(
                    format_theme_summary(
                        negative_reviews
                    )
                )}"
                "</li>"
            )
        ])

    return f"""
    <li style="margin-bottom: 22px;">
        <strong style="font-size: 17px;">
            {escape(platform_name)}
        </strong>

        <ul style="
            margin-top: 8px;
            padding-left: 24px;
        ">
            {''.join(bullet_items)}
        </ul>
    </li>
    """

def build_biweekly_report(
    run_date=None,
    start_date=None,
    end_date=None
):
    if start_date is None and end_date is None:
        start_date, end_date = get_reporting_period(
            run_date=run_date
        )

    elif start_date is None or end_date is None:
        raise ValueError(
            "Both start_date and end_date must be provided."
        )

    start_date = pd.Timestamp(
        start_date
    ).date()

    end_date = pd.Timestamp(
        end_date
    ).date()

    if start_date > end_date:
        raise ValueError(
            "The start date cannot be after the end date."
        )

    product_sections = []

    for product_name, platforms in PRODUCTS.items():
        retailer_sections = []

        for platform_name, product_url in platforms.items():
            if not is_valid_product_url(
                product_url
            ):
                continue

            retailer_sections.append(
                build_platform_section(
                    product_name=product_name,
                    platform_name=platform_name,
                    start_date=start_date,
                    end_date=end_date
                )
            )

        if not retailer_sections:
            retailer_sections.append(
                """
                <li>
                    <strong>No active retailers</strong>
                </li>
                """
            )

        product_sections.append(
            f"""
            <div style="margin-top: 30px;">
                <h2 style="
                    margin: 0 0 12px 0;
                    padding-bottom: 7px;
                    border-bottom: 2px solid #333333;
                    font-size: 21px;
                ">
                    <strong>
                        {escape(product_name)}
                    </strong>
                </h2>

                <ol style="
                    margin-top: 10px;
                    padding-left: 30px;
                ">
                    {''.join(retailer_sections)}
                </ol>
            </div>
            """
        )

    return f"""
    <div style="
        max-width: 850px;
        margin: 0 auto;
        padding: 20px;
        font-family: Arial, Helvetica, sans-serif;
        line-height: 1.5;
        color: #222222;
        background-color: #ffffff;
    ">
        <div style="
            padding: 20px;
            background-color: #f3f3f3;
            border-radius: 8px;
        ">
            <h1 style="
                margin: 0 0 8px 0;
                font-size: 26px;
                font-weight: bold;
            ">
                Ole Henriksen Biweekly Review Report
            </h1>

            <p style="margin: 0;">
                <strong>Reporting period:</strong>
                {start_date.strftime("%B %d, %Y")}
                –
                {end_date.strftime("%B %d, %Y")}
            </p>
        </div>

        {''.join(product_sections)}

        <p style="
            margin-top: 32px;
            padding-top: 12px;
            border-top: 1px solid #dddddd;
            font-size: 12px;
            color: #666666;
        ">
            Review counts and incentivized averages use reviews
            published during the selected period. Overall rating
            change compares the cumulative calculated rating at
            the beginning of the first day with the cumulative
            calculated rating through the final day.
        </p>
    </div>
    """

def main():
    report = build_biweekly_report()

    # Preview only. No email is sent at this stage.
    print(report)


if __name__ == "__main__":
    main()
