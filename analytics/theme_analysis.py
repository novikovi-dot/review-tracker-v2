import re

import pandas as pd


THEME_PATTERNS = {
    "Brightening and Glow": [
        r"\bbright(?:en|ening|ens|er)?\b",
        r"\bglow(?:ing|y)?\b",
        r"\bradiant\b",
        r"\bdark circles?\b",
        r"\bhyperpigmentation\b"
    ],
    "Hydration": [
        r"\bhydrat(?:e|ed|es|ing|ion)?\b",
        r"\bmoistur(?:e|ed|ized|izer|izing)?\b",
        r"\bdryness\b",
        r"\bdry skin\b",
        r"\bplump(?:ed|ing)?\b"
    ],
    "Texture and Feel": [
        r"\btexture\b",
        r"\blightweight\b",
        r"\bheavy\b",
        r"\bgreasy\b",
        r"\bsticky\b",
        r"\btacky\b",
        r"\bsmooth\b",
        r"\babsorbs?\b",
        r"\bpill(?:s|ing|ed)?\b"
    ],
    "Scent": [
        r"\bscent(?:ed)?\b",
        r"\bsmell(?:s|ed)?\b",
        r"\bfragrance\b",
        r"\bperfume(?:d)?\b"
    ],
    "Packaging": [
        r"\bpackag(?:e|ing)\b",
        r"\bpump\b",
        r"\bjar\b",
        r"\bbottle\b",
        r"\bcap\b",
        r"\bapplicator\b",
        r"\bdispenser\b",
        r"\bleak(?:s|ing|ed)?\b",
        r"\bbroken\b",
        r"\bcrack(?:ed|ing)?\b"
    ],
    "Irritation and Sensitivity": [
        r"\birritat(?:e|ed|es|ing|ion)?\b",
        r"\bsting(?:s|ing)?\b",
        r"\bburn(?:s|ed|ing)?\b",
        r"\bbreakout(?:s)?\b",
        r"\brash\b",
        r"\bredness\b",
        r"\bsensitive\b",
        r"\ballergic\b"
    ],
    "Price and Value": [
        r"\bprice\b",
        r"\bexpensive\b",
        r"\boverpriced\b",
        r"\bworth\b",
        r"\bvalue\b",
        r"\baffordable\b"
    ],
    "Effectiveness and Results": [
        r"\bwork(?:s|ed|ing)?\b",
        r"\beffective\b",
        r"\bresults?\b",
        r"\bdifference\b",
        r"\bimprov(?:e|ed|ement|ing)\b",
        r"\bnoticeable\b"
    ],
    "Repurchase and Loyalty": [
        r"\brepurchase\b",
        r"\bbuy again\b",
        r"\bpurchase again\b",
        r"\bholy grail\b",
        r"\bstaple\b",
        r"\bfavorite\b",
        r"\bgo-to\b"
    ],
    "Application and Makeup": [
        r"\bapplication\b",
        r"\bapply\b",
        r"\bunder makeup\b",
        r"\bconcealer\b",
        r"\bfoundation\b",
        r"\bmakeup\b"
    ]
}


ALERT_THEMES = {
    "Packaging",
    "Irritation and Sensitivity",
    "Scent",
    "Texture and Feel"
}


def _get_rating_column(df):
    if "rating" in df.columns:
        return "rating"

    if "Rating" in df.columns:
        return "Rating"

    return None


def _text_column(df):
    title = df.get(
        "review_title",
        pd.Series("", index=df.index, dtype=str)
    ).fillna("").astype(str)

    body = df.get(
        "review_text",
        pd.Series("", index=df.index, dtype=str)
    ).fillna("").astype(str)

    return (title + " " + body).str.strip()


def _example_text(row):
    body = row.get("review_text")
    title = row.get("review_title")

    if body is not None and pd.notna(body) and str(body).strip():
        text = str(body).strip()

    elif title is not None and pd.notna(title):
        text = str(title).strip()

    else:
        return ""

    if len(text) > 250:
        return text[:247] + "..."

    return text


def calculate_new_review_metrics(new_reviews_df):
    empty_metrics = {
        "new_review_count": 0,
        "new_review_average_rating": None,
        "five_star_new_reviews": 0,
        "four_star_new_reviews": 0,
        "three_star_new_reviews": 0,
        "two_star_new_reviews": 0,
        "one_star_new_reviews": 0
    }

    if new_reviews_df is None or new_reviews_df.empty:
        return empty_metrics

    rating_column = _get_rating_column(new_reviews_df)

    if rating_column is None:
        return {
            **empty_metrics,
            "new_review_count": len(new_reviews_df)
        }

    ratings = pd.to_numeric(
        new_reviews_df[rating_column],
        errors="coerce"
    )

    return {
        "new_review_count": len(new_reviews_df),
        "new_review_average_rating": (
            round(float(ratings.mean()), 2)
            if ratings.notna().any()
            else None
        ),
        "five_star_new_reviews": int((ratings == 5).sum()),
        "four_star_new_reviews": int((ratings == 4).sum()),
        "three_star_new_reviews": int((ratings == 3).sum()),
        "two_star_new_reviews": int((ratings == 2).sum()),
        "one_star_new_reviews": int((ratings == 1).sum())
    }


def analyze_themes(new_reviews_df):
    columns = [
        "Theme",
        "Total Mentions",
        "Positive Reviews",
        "Negative Reviews",
        "Mixed Reviews",
        "Share of New Reviews",
        "Negative Share of Theme",
        "Alert",
        "Positive Example",
        "Negative Example"
    ]

    if new_reviews_df is None or new_reviews_df.empty:
        return pd.DataFrame(columns=columns)

    df = new_reviews_df.copy()
    df["combined_text"] = _text_column(df)

    rating_column = _get_rating_column(df)

    if rating_column:
        df["rating_number"] = pd.to_numeric(
            df[rating_column],
            errors="coerce"
        )
    else:
        df["rating_number"] = pd.Series(
            index=df.index,
            dtype=float
        )

    total_reviews = len(df)
    rows = []

    for theme, patterns in THEME_PATTERNS.items():
        regex = re.compile(
            "(?:" + "|".join(patterns) + ")",
            flags=re.IGNORECASE
        )

        matched = df[
            df["combined_text"].str.contains(
                regex,
                na=False
            )
        ]

        if matched.empty:
            continue

        positive = matched[
            matched["rating_number"] >= 4
        ]

        negative = matched[
            matched["rating_number"] <= 2
        ]

        mixed = matched[
            (matched["rating_number"] == 3)
            | matched["rating_number"].isna()
        ]

        negative_share = round(
            len(negative) / len(matched) * 100,
            1
        )

        alert = ""

        if theme in ALERT_THEMES:
            if len(negative) >= 3:
                alert = "High concern"

            elif len(negative) >= 2:
                alert = "Monitor"

            elif (
                len(negative) == 1
                and negative_share >= 50
            ):
                alert = "Monitor"

        positive_example = (
            _example_text(positive.iloc[0])
            if not positive.empty
            else ""
        )

        negative_example = (
            _example_text(negative.iloc[0])
            if not negative.empty
            else ""
        )

        rows.append({
            "Theme": theme,
            "Total Mentions": len(matched),
            "Positive Reviews": len(positive),
            "Negative Reviews": len(negative),
            "Mixed Reviews": len(mixed),
            "Share of New Reviews": round(
                len(matched) / total_reviews * 100,
                1
            ),
            "Negative Share of Theme": negative_share,
            "Alert": alert,
            "Positive Example": positive_example,
            "Negative Example": negative_example
        })

    if not rows:
        return pd.DataFrame(columns=columns)

    return (
        pd.DataFrame(rows)
        .sort_values(
            [
                "Negative Reviews",
                "Total Mentions",
                "Positive Reviews"
            ],
            ascending=[
                False,
                False,
                False
            ]
        )
        .reset_index(drop=True)
    )


def get_emerging_issue_alerts(theme_df):
    if theme_df is None or theme_df.empty:
        return []

    alerts = theme_df[
        theme_df["Alert"].isin(
            ["Monitor", "High concern"]
        )
    ]

    if alerts.empty:
        return []

    results = []

    for _, row in alerts.iterrows():
        results.append({
            "theme": row["Theme"],
            "alert_level": row["Alert"],
            "negative_reviews": int(
                row["Negative Reviews"]
            ),
            "total_mentions": int(
                row["Total Mentions"]
            ),
            "negative_share": float(
                row["Negative Share of Theme"]
            ),
            "example": row["Negative Example"]
        })

    return results


def build_retailer_update(
    source,
    new_review_count,
    theme_df,
    new_review_metrics=None
):
    if new_review_count == 0:
        return f"{source}: No new reviews were detected."

    sentence = (
        f"{source} received "
        f"{new_review_count} new reviews."
    )

    if new_review_metrics:
        new_average = new_review_metrics.get(
            "new_review_average_rating"
        )

        if new_average is not None:
            sentence += (
                f" Their average rating was "
                f"{new_average:.2f}."
            )

        one_two_star_count = (
            new_review_metrics.get(
                "one_star_new_reviews",
                0
            )
            + new_review_metrics.get(
                "two_star_new_reviews",
                0
            )
        )

        if one_two_star_count > 0:
            sentence += (
                f" {one_two_star_count} of the new "
                "reviews were one or two stars."
            )

    if theme_df is None or theme_df.empty:
        sentence += (
            " There was not enough theme data "
            "to create a detailed summary."
        )

        return sentence

    positive_themes = (
        theme_df[
            theme_df["Positive Reviews"] > 0
        ]
        .sort_values(
            [
                "Positive Reviews",
                "Total Mentions"
            ],
            ascending=False
        )
        .head(2)["Theme"]
        .tolist()
    )

    negative_themes = (
        theme_df[
            theme_df["Negative Reviews"] > 0
        ]
        .sort_values(
            [
                "Negative Reviews",
                "Total Mentions"
            ],
            ascending=False
        )
        .head(2)["Theme"]
        .tolist()
    )

    if positive_themes:
        sentence += (
            " Reviewers most frequently praised "
            + " and ".join(positive_themes)
            + "."
        )

    if negative_themes:
        sentence += (
            " The most common concerns involved "
            + " and ".join(negative_themes)
            + "."
        )

    alerts = get_emerging_issue_alerts(theme_df)

    if alerts:
        alert_names = [
            alert["theme"]
            for alert in alerts[:2]
        ]

        sentence += (
            " Monitor "
            + " and ".join(alert_names)
            + " in the next reporting period."
        )

    return sentence
