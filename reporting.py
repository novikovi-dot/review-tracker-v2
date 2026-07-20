import pandas as pd


def get_rating_column(df):
    if df is None:
        return None

    for column_name in [
        "rating",
        "Rating",
        "score"
    ]:
        if column_name in df.columns:
            return column_name

    return None


def calculate_period_rating_change(
    reviews_df,
    start_date,
    end_date
):
    if reviews_df is None or reviews_df.empty:
        return None

    working_df = reviews_df.copy()

    if "review_date" not in working_df.columns:
        return None

    rating_column = get_rating_column(
        working_df
    )

    if rating_column is None:
        return None

    working_df["parsed_review_date"] = pd.to_datetime(
        working_df["review_date"],
        utc=True,
        errors="coerce"
    )

    working_df["numeric_rating"] = pd.to_numeric(
        working_df[rating_column],
        errors="coerce"
    )

    working_df = working_df.dropna(
        subset=[
            "parsed_review_date",
            "numeric_rating"
        ]
    )

    if working_df.empty:
        return None

    selected_start = pd.Timestamp(
        start_date,
        tz="UTC"
    )

    selected_end_exclusive = (
        pd.Timestamp(
            end_date,
            tz="UTC"
        )
        + pd.Timedelta(days=1)
    )

    period_length_days = (
        pd.Timestamp(end_date)
        - pd.Timestamp(start_date)
    ).days + 1

    previous_start = (
        selected_start
        - pd.Timedelta(
            days=period_length_days
        )
    )

    baseline_reviews = working_df[
        working_df["parsed_review_date"]
        < selected_start
    ]

    current_reviews = working_df[
        working_df["parsed_review_date"]
        < selected_end_exclusive
    ]

    previous_period_reviews = working_df[
        (
            working_df["parsed_review_date"]
            >= previous_start
        )
        & (
            working_df["parsed_review_date"]
            < selected_start
        )
    ]

    selected_period_reviews = working_df[
        (
            working_df["parsed_review_date"]
            >= selected_start
        )
        & (
            working_df["parsed_review_date"]
            < selected_end_exclusive
        )
    ]

    if (
        baseline_reviews.empty
        or current_reviews.empty
    ):
        return None

    baseline_rating = float(
        baseline_reviews[
            "numeric_rating"
        ].mean()
    )

    current_rating = float(
        current_reviews[
            "numeric_rating"
        ].mean()
    )

    return {
        "baseline_rating": baseline_rating,
        "current_rating": current_rating,
        "rating_change": (
            current_rating
            - baseline_rating
        ),
        "previous_period_start": (
            previous_start
            .date()
            .isoformat()
        ),
        "previous_period_end": (
            (
                selected_start
                - pd.Timedelta(days=1)
            )
            .date()
            .isoformat()
        ),
        "selected_period_start": (
            selected_start
            .date()
            .isoformat()
        ),
        "selected_period_end": (
            (
                selected_end_exclusive
                - pd.Timedelta(days=1)
            )
            .date()
            .isoformat()
        ),
        "previous_period_review_count": int(
            len(previous_period_reviews)
        ),
        "selected_period_review_count": int(
            len(selected_period_reviews)
        )
    }
