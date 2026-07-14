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
        r"\bmoistur(?:e|ized|izer|izing)?\b",
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
        r"\bleak(?:s|ing|ed)?\b"
    ],
    "Irritation and Sensitivity": [
        r"\birritat(?:e|ed|es|ing|ion)?\b",
        r"\bsting(?:s|ing)?\b",
        r"\bburn(?:s|ed|ing)?\b",
        r"\bbreakout(?:s)?\b",
        r"\brash\b",
        r"\bredness\b",
        r"\bsensitive\b"
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

    text = body if pd.notna(body) and str(body).strip() else title

    if text is None or pd.isna(text):
        return ""

    text = str(text).strip()

    if len(text) > 250:
        return text[:247] + "..."

    return text


def analyze_themes(new_reviews_df):
    columns = [
        "Theme",
        "Total Mentions",
        "Positive Reviews",
        "Negative Reviews",
        "Mixed Reviews",
        "Share of New Reviews",
        "Positive Example",
        "Negative Example"
    ]

    if new_reviews_df is None or new_reviews_df.empty:
        return pd.DataFrame(columns=columns)

    df = new_reviews_df.copy()
    df["combined_text"] = _text_column(df)

    df["rating_number"] = pd.to_numeric(
        df.get(
            "rating",
            pd.Series(index=df.index, dtype=float)
        ),
        errors="coerce"
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

        positive = matched[matched["rating_number"] >= 4]
        negative = matched[matched["rating_number"] <= 2]
        mixed = matched[
            (matched["rating_number"] == 3) |
            (matched["rating_number"].isna())
        ]

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
            "Positive Example": positive_example,
            "Negative Example": negative_example
        })

    if not rows:
        return pd.DataFrame(columns=columns)

    return (
        pd.DataFrame(rows)
        .sort_values(
            ["Total Mentions", "Positive Reviews"],
            ascending=False
        )
        .reset_index(drop=True)
    )


def build_retailer_update(source, new_review_count, theme_df):
    if new_review_count == 0:
        return f"{source}: No new reviews were detected."

    if theme_df is None or theme_df.empty:
        return (
            f"{source} received {new_review_count} new reviews. "
            "There was not enough theme data to create a summary."
        )

    positive_themes = (
        theme_df[theme_df["Positive Reviews"] > 0]
        .sort_values("Positive Reviews", ascending=False)
        .head(2)["Theme"]
        .tolist()
    )

    negative_themes = (
        theme_df[theme_df["Negative Reviews"] > 0]
        .sort_values("Negative Reviews", ascending=False)
        .head(2)["Theme"]
        .tolist()
    )

    sentence = f"{source} received {new_review_count} new reviews."

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

    return sentence
