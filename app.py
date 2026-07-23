import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from io import BytesIO
from datetime import date, timedelta

from products import PRODUCTS

import analytics.biweekly_email as biweekly_email

from scrapers.ulta import (
    scrape_product as scrape_ulta_product,
    clean_filename
)

from analytics.theme_analysis import (
    analyze_themes,
    build_retailer_update,
    calculate_new_review_metrics,
    get_emerging_issue_alerts,
    calculate_incentive_metrics
)

from analytics.reporting import (
    calculate_period_rating_change
)

from database.db import (
    save_reviews,
    save_snapshot,
    get_snapshot_changes,
    get_period_snapshot_change,
    load_reviews_by_date_range,
    load_all_reviews
)

from scrapers.sephora import scrape_sephora_product
from scrapers.brand import scrape_brand_product


st.set_page_config(
    page_title="Beauty Review Tracker",
    page_icon="⭐",
    layout="centered"
)

APP_PASSWORD = st.secrets["APP_PASSWORD"]

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 Beauty Review Tracker")

        password = st.text_input(
            "Enter password:",
            type="password"
        )

        if st.button("Login"):
            if password == APP_PASSWORD:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")

        st.stop()

def scrape_selected_source(
    source,
    link,
    delay_seconds,
    review_progress_bar,
    review_progress_text
):
    if source == "Ulta":
        df, working_id = scrape_ulta_product(
            link,
            delay_seconds,
            review_progress_bar,
            review_progress_text
        )
        return df

    if source == "Sephora":
        return scrape_sephora_product(
            link,
            delay_seconds,
            review_progress_bar,
            review_progress_text
        )

    if source == "Brand Website":
        return scrape_brand_product(
            link,
            delay_seconds,
            review_progress_bar,
            review_progress_text
        )

    st.error("Unknown source selected.")
    return None

def get_rating_column(df):
    if "rating" in df.columns:
        return "rating"

    if "Rating" in df.columns:
        return "Rating"

    return None

def format_optional_rating(value):
    if value is None:
        return "N/A"

    try:
        if pd.isna(value):
            return "N/A"
    except (TypeError, ValueError):
        return "N/A"

    return f"{float(value):.2f}"


def format_optional_delta(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None

    return f"{float(value):+.2f}"

def summarize_retailer(
    df,
    source,
    product_name,
    product_url
):
    rating_col = get_rating_column(df)

    if rating_col:
        ratings = pd.to_numeric(
            df[rating_col],
            errors="coerce"
        )

        avg_rating = (
            round(ratings.mean(), 2)
            if ratings.notna().any()
            else ""
        )

        five_star = int((ratings == 5).sum())
        four_star = int((ratings == 4).sum())
        three_star = int((ratings == 3).sum())
        two_star = int((ratings == 2).sum())
        one_star = int((ratings == 1).sum())

    else:
        avg_rating = ""
        five_star = 0
        four_star = 0
        three_star = 0
        two_star = 0
        one_star = 0

    if source == "Brand Website":
        recommended_rate = "N/A"
    else:
        recommended_rate = df.attrs.get(
            "official_recommendation_rate",
            ""
        )

    return pd.DataFrame({
        "Metric": [
            "Product",
            "Retailer",
            "Product URL",
            "Total Reviews",
            "Average Rating",
            "5 Star Reviews",
            "4 Star Reviews",
            "3 Star Reviews",
            "2 Star Reviews",
            "1 Star Reviews",
            "Recommendation Rate"
        ],
        "Value": [
            product_name,
            source,
            product_url,
            len(df),
            avg_rating,
            five_star,
            four_star,
            three_star,
            two_star,
            one_star,
            recommended_rate
        ]
    })

def create_rating_breakdown(df):
    rating_col = get_rating_column(df)

    if not rating_col:
        return pd.DataFrame(
            columns=[
                "Rating",
                "Review Count",
                "Percentage"
            ]
        )

    ratings = pd.to_numeric(
        df[rating_col],
        errors="coerce"
    )

    breakdown = (
        ratings
        .value_counts()
        .sort_index(ascending=False)
        .reset_index()
    )

    breakdown.columns = [
        "Rating",
        "Review Count"
    ]

    if len(df) > 0:
        breakdown["Percentage"] = (
            breakdown["Review Count"] / len(df)
        )

    return breakdown

def create_combined_excel_report(
    retailer_data,
    retailer_links,
    product_name,
    new_reviews_by_source,
    theme_summaries,
    retailer_updates
):
    output = BytesIO()
    comparison_rows = []

    for source, df in retailer_data.items():
        rating_col = get_rating_column(df)

        if rating_col:
            ratings = pd.to_numeric(
                df[rating_col],
                errors="coerce"
            )

            avg_rating = (
                round(ratings.mean(), 2)
                if ratings.notna().any()
                else ""
            )
        else:
            avg_rating = ""

        new_reviews_df = new_reviews_by_source.get(
            source,
            pd.DataFrame()
        )

        new_review_count = (
            len(new_reviews_df)
            if new_reviews_df is not None
            else 0
        )

        comparison_rows.append({
            "Product": product_name,
            "Retailer": source,
            "Total Reviews": len(df),
            "New Reviews": new_review_count,
            "Average Rating": avg_rating,
            "Product URL": retailer_links.get(source, "")
        })

    comparison_df = pd.DataFrame(comparison_rows)

    updates_df = pd.DataFrame([
        {
            "Retailer": source,
            "New Reviews": (
                len(new_reviews_by_source.get(source, pd.DataFrame()))
                if new_reviews_by_source.get(source) is not None
                else 0
            ),
            "Update": update
        }
        for source, update in retailer_updates.items()
    ])

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:
        comparison_df.to_excel(
            writer,
            index=False,
            sheet_name="Retailer Comparison"
        )

        updates_df.to_excel(
            writer,
            index=False,
            sheet_name="New Review Summary"
        )

        # Existing retailer sheets
        for source, df in retailer_data.items():
            summary_df = summarize_retailer(
                df=df,
                source=source,
                product_name=product_name,
                product_url=retailer_links.get(source, "")
            )

            rating_breakdown_df = create_rating_breakdown(df)

            summary_sheet = f"{source} Summary"[:31]
            reviews_sheet = f"{source} Reviews"[:31]
            ratings_sheet = f"{source} Ratings"[:31]

            summary_df.to_excel(
                writer,
                index=False,
                sheet_name=summary_sheet
            )

            rating_breakdown_df.to_excel(
                writer,
                index=False,
                sheet_name=ratings_sheet
            )

            df.to_excel(
                writer,
                index=False,
                sheet_name=reviews_sheet
            )

        # New-review sheets
        for source in retailer_data:
            new_reviews_df = new_reviews_by_source.get(
                source,
                pd.DataFrame()
            )

            new_reviews_sheet = (
                f"{source} New Reviews"[:31]
            )

            if (
                new_reviews_df is not None
                and not new_reviews_df.empty
            ):
                new_reviews_df.to_excel(
                    writer,
                    index=False,
                    sheet_name=new_reviews_sheet
                )
            else:
                pd.DataFrame({
                    "Status": [
                        "No new reviews were detected."
                    ]
                }).to_excel(
                    writer,
                    index=False,
                    sheet_name=new_reviews_sheet
                )

        # Theme-analysis sheets
        for source in retailer_data:
            theme_df = theme_summaries.get(
                source,
                pd.DataFrame()
            )

            themes_sheet = f"{source} Themes"[:31]

            if (
                theme_df is not None
                and not theme_df.empty
            ):
                theme_df.to_excel(
                    writer,
                    index=False,
                    sheet_name=themes_sheet
                )
            else:
                pd.DataFrame({
                    "Status": [
                        "No new-review themes were detected."
                    ]
                }).to_excel(
                    writer,
                    index=False,
                    sheet_name=themes_sheet
                )

        # Format every worksheet
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]

            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions

            for column_cells in worksheet.columns:
                max_length = 0
                column_letter = (
                    column_cells[0].column_letter
                )

                for cell in column_cells:
                    if cell.value is not None:
                        max_length = max(
                            max_length,
                            len(str(cell.value))
                        )

                    cell.alignment = (
                        cell.alignment.copy(
                            wrap_text=True,
                            vertical="top"
                        )
                    )

                worksheet.column_dimensions[
                    column_letter
                ].width = min(max_length + 2, 70)

    output.seek(0)
    return output

check_password()

st.title("⭐ Beauty Review Tracker")

st.write(
    "Select a product and choose which retailer "
    "platforms to include."
)

product_names = list(PRODUCTS.keys())

selected_product = st.selectbox(
    "Product",
    product_names
)

product_info = PRODUCTS[selected_product]

platforms = [
    "Ulta",
    "Sephora",
    "Brand Website"
]

for platform in platforms:
    key = f"platform_{platform}"

    if key not in st.session_state:
        st.session_state[key] = True


button_col1, button_col2 = st.columns(2)

with button_col1:
    if st.button(
        "Select All",
        use_container_width=True
    ):
        for platform in platforms:
            st.session_state[
                f"platform_{platform}"
            ] = True

        st.rerun()


with button_col2:
    if st.button(
        "Clear All",
        use_container_width=True
    ):
        for platform in platforms:
            st.session_state[
                f"platform_{platform}"
            ] = False

        st.rerun()


st.write("Platforms")

col1, col2, col3 = st.columns(3)

with col1:
    st.checkbox(
        "Ulta",
        key="platform_Ulta"
    )

with col2:
    st.checkbox(
        "Sephora",
        key="platform_Sephora"
    )

with col3:
    st.checkbox(
        "Brand Website",
        key="platform_Brand Website"
    )


selected_platforms = [
    platform
    for platform in platforms
    if st.session_state[f"platform_{platform}"]
]


with st.expander("Selected product links"):
    for platform in platforms:
        link = product_info.get(platform, "")

        if link:
            st.write(f"**{platform}:** {link}")
        else:
            st.write(
                f"**{platform}:** No link saved"
            )
with st.expander("Settings"):
    delay_seconds = st.slider(
        "Delay between requests",
        min_value=0.1,
        max_value=2.0,
        value=0.25,
        step=0.05
    )

    show_preview = st.checkbox(
        "Show preview table",
        value=True
    )


st.subheader("Review reporting period")

default_end_date = date.today()
default_start_date = (
    default_end_date - timedelta(days=13)
)

all_time_col, start_date_col, end_date_col = st.columns(
    [0.8, 1.4, 1.4]
)

with all_time_col:
    report_all_time = st.checkbox(
        "All time",
        value=False
    )

with start_date_col:
    report_start_date = st.date_input(
        "Start date",
        value=default_start_date,
        max_value=default_end_date,
        disabled=report_all_time
    )

with end_date_col:
    report_end_date = st.date_input(
        "End date",
        value=default_end_date,
        max_value=default_end_date,
        disabled=report_all_time
    )

if (
    not report_all_time
    and report_start_date > report_end_date
):
    st.error(
        "The start date cannot be later than the end date."
    )
    st.stop()

if st.button(
    "Generate Product Report",
    use_container_width=True
):
    links = []

    for platform in selected_platforms:
        link = product_info.get(platform)

        if link:
            links.append((platform, link))

    if not links:
        st.error(
            "Please select at least one platform "
            "with a saved link."
        )
        st.stop()

    product_progress_bar = st.progress(0)
    product_progress_text = st.empty()

    review_progress_bar = st.progress(0)
    review_progress_text = st.empty()

    results_summary = []

    retailer_data = {}
    retailer_links = {}

    # New Step 3 containers
    new_reviews_by_source = {}
    theme_summaries = {}
    retailer_updates = {}

    for index, (source, link) in enumerate(
        links,
        start=1
    ):
        product_progress_text.write(
            f"Platform {index} of {len(links)}: "
            f"{source}"
        )

        product_progress_bar.progress(
            (index - 1) / len(links)
        )

        review_progress_bar.progress(0)
        review_progress_text.write(
            "Finding reviews..."
        )

        df = scrape_selected_source(
            source,
            link,
            delay_seconds,
            review_progress_bar,
            review_progress_text
        )

        if source == "Ulta" and df is not None:
            st.write(
                "Ulta reported total:",
                df.attrs.get(
                    "official_total_reviews"
                )
            )
        
            st.write(
                "Unique reviews downloaded:",
                df.attrs.get(
                    "downloaded_review_count",
                    len(df)
                )
            )
        
            st.write(
                "Ulta official rating:",
                df.attrs.get(
                    "official_average_rating"
                )
            )
        if df is None or df.empty:
            results_summary.append({
                "Product": selected_product,
                "Source": source,
                "Status": "No reviews found",
                "Reviews": 0,
                "New Reviews": 0
            })
            continue
        if source == "Ulta":
            st.write(
                "Official Ulta rating received:",
                df.attrs.get("official_average_rating")
            )

        if "review_id" in df.columns:
            df = df.drop_duplicates(
                subset=["review_id"]
            )
        else:
            df = df.drop_duplicates()

        saved_count = 0
        new_reviews_df = pd.DataFrame()
        theme_summary_df = pd.DataFrame()

        new_review_metrics = calculate_new_review_metrics(
            new_reviews_df
        )

        emerging_alerts = []

        snapshot_changes = None
        current_rating = None
        rating_change = None
        previous_rating = None
        previous_scrape_date = None

        retailer_update = (
            f"{source}: No update was generated."
        )

        incentive_metrics = calculate_incentive_metrics(
            pd.DataFrame()
        )

        try:
            save_result = save_reviews(
                df=df,
                source=source,
                product_name=selected_product,
                product_url=link
            )

            if (
                isinstance(save_result, tuple)
                and len(save_result) == 2
            ):
                saved_count, new_reviews_df = save_result

            else:
                saved_count = int(save_result or 0)

                st.warning(
                    "Theme analysis requires the updated "
                    "save_reviews() function. "
                    "The database count was saved, but the "
                    "new-review records were not returned."
                )
            save_snapshot(
                df=df,
                source=source,
                product_name=selected_product,
                product_url=link
            )

            snapshot_changes = get_snapshot_changes(
                product_name=selected_product,
                source=source
            )
            
            rating_column = get_rating_column(df)

            if rating_column:
                numeric_ratings = pd.to_numeric(
                    df[rating_column],
                    errors="coerce"
                )

                if numeric_ratings.notna().any():
                    current_rating = float(
                        numeric_ratings.mean()
                    )

            if snapshot_changes:
                snapshot_current_rating = (
                    snapshot_changes.get(
                        "current_average_rating"
                    )
                )

                if snapshot_current_rating is not None:
                    current_rating = (
                        snapshot_current_rating
                    )

                rating_change = snapshot_changes.get(
                    "rating_change"
                )

                previous_rating = snapshot_changes.get(
                    "previous_average_rating"
                )

                previous_scrape_date = (
                    snapshot_changes.get(
                        "previous_scrape_date"
                    )
                )

            st.write(
                "Rating change since last saved snapshot"
            )

            snapshot_col1, snapshot_col2 = st.columns(2)

            with snapshot_col1:
                st.metric(
                    label="Current overall rating",
                    value=(
                        f"{current_rating:.2f}"
                        if current_rating is not None
                        else "N/A"
                    ),
                    delta=(
                        f"{rating_change:+.2f}"
                        if rating_change is not None
                        else None
                    )
                )

            with snapshot_col2:
                st.metric(
                    label=(
                        f"Last saved snapshot "
                        f"({previous_scrape_date})"
                        if previous_scrape_date
                        else "Last saved snapshot"
                    ),
                    value=(
                        f"{previous_rating:.2f}"
                        if previous_rating is not None
                        else "N/A"
                    )
                )

            if snapshot_changes is None:
                st.caption(
                    "No earlier saved snapshot is available "
                    "for comparison."
                )
            else:
                st.caption(
                    "This compares the current scrape with "
                    "the most recent saved snapshot."
                )
            
            
            if report_all_time:
                reporting_reviews_df = load_all_reviews(
                    product_name=selected_product,
                    source=source
                )
            else:
                reporting_reviews_df = load_reviews_by_date_range(
                    product_name=selected_product,
                    source=source,
                    start_date=report_start_date,
                    end_date=report_end_date
                )

            if report_all_time:
                st.info(
                    f"{source}: {len(reporting_reviews_df)} "
                    "reviews included across all available dates."
                )
            else:
                st.info(
                    f"{source}: {len(reporting_reviews_df)} "
                    "reviews have posting dates between "
                    f"{report_start_date} and "
                    f"{report_end_date}."
                )

            incentive_metrics = calculate_incentive_metrics(
                reporting_reviews_df
            )

            new_review_metrics = calculate_new_review_metrics(
                reporting_reviews_df
            )

            theme_summary_df = analyze_themes(
                reporting_reviews_df
            )

            if not reporting_reviews_df.empty:
                verification_columns = [
                    column
                    for column in [
                      "review_id",
                      "review_date",
                      "rating",
                      "review_title",
                      "review_text",
                      "reviewer_name"
                    ]
                    if column in reporting_reviews_df.columns
                ]
                with st.expander(
                    f"{source} reviews in selected date range"
                ):
                    st.dataframe(
                        reporting_reviews_df[
                            verification_columns
                        ].sort_values(
                            "review_date",
                            ascending=False
                        ),
                        use_container_width=True
                    )

            if not reporting_reviews_df.empty:
                st.write("Incentivized review breakdown")

                incentive_col1, incentive_col2, incentive_col3 = (
                    st.columns(3)
                )

                with incentive_col1:
                    st.metric(
                        "Incentivized",
                        incentive_metrics[
                            "incentivized_reviews"
                        ]
                    )

                with incentive_col2:
                     st.metric(
                        "Non-Incentivized",
                        incentive_metrics[
                            "non_incentivized_reviews"
                        ]
                     )

                with incentive_col3:
                     st.metric(
                         "Unknown",
                         incentive_metrics[
                            "unknown_incentive_reviews"
                         ]
                     )

                rating_col1, rating_col2 = st.columns(2)

                with rating_col1:
                    incentivized_average = incentive_metrics[
                        "incentivized_average_rating"
                    ]

                    st.metric(
                        "Incentivized Avg. Rating",
                        (
                            f"{incentivized_average:.2f}"
                            if incentivized_average is not None
                            else "N/A"
                        )
                    )

                with rating_col2:
                     organic_average = incentive_metrics[
                         "non_incentivized_average_rating"
                     ]

                     st.metric(
                        "Non-Incentivized Avg. Rating",
                        (
                            f"{organic_average:.2f}"
                            if organic_average is not None
                            else "N/A"
                        )
                     )
                    

            emerging_alerts = get_emerging_issue_alerts(
                theme_summary_df
            )

            retailer_update = build_retailer_update(
                source=source,
                new_review_count=len(reporting_reviews_df),
                theme_df=theme_summary_df,
                new_review_metrics=new_review_metrics
            )

            st.caption(
                f"Database maintenance: {saved_count} previously "
                "missing review records were saved."
            )
            
            st.info(
                f"{source}: {len(reporting_reviews_df)} reviews "
                f"were posted from {report_start_date} "
                f"through {report_end_date}."
            )
            
            if not report_all_time:
                rating_comparison = get_period_snapshot_change(
                    product_name=selected_product,
                    source=source,
                    start_date=report_start_date,
                    end_date=report_end_date
                )

                st.write(
                    "Rating change from the start of the selected period"
                )

                if rating_comparison is None:
                    st.info(
                        "The selected-period comparison could not be "
                        "calculated because there are not enough dated "
                        "historical reviews."
                    )
                    
                else:
                    period_current_rating = rating_comparison.get(
                        "current_rating"
                    )
                    
                    period_baseline_rating = rating_comparison.get(
                        "baseline_rating"
                    )
                    
                    period_rating_change = rating_comparison.get(
                        "rating_change"
                    )
                    
                    baseline_end_date = rating_comparison.get(
                        "previous_period_end"
                    )
                    
                    period_col1, period_col2 = st.columns(2)
                    
                    with period_col1:
                        st.metric(
                            label=f"Rating through {report_end_date}",
                            value=format_optional_rating(
                                period_current_rating
                            ),
                            delta=format_optional_delta(
                                period_rating_change
                            )
                        )
                    
                    with period_col2:
                        baseline_label = (
                            f"Baseline through {baseline_end_date}"
                            if baseline_end_date
                            else "Baseline rating"
                        )
                    
                        st.metric(
                            label=baseline_label,
                            value=format_optional_rating(
                                period_baseline_rating
                            )
                        )
                    
                    if period_baseline_rating is None:
                        st.caption(
                            "No cumulative rating baseline was available "
                            "before the selected reporting period."
                        )
                    
                    else:
                        st.caption(
                            f"Selected period: {report_start_date} through "
                            f"{report_end_date}. The baseline is the "
                            f"cumulative rating through {baseline_end_date}, "
                            "which is the day before the selected period began."
                        )
        except Exception as error:
            saved_count = 0
            new_reviews_df = pd.DataFrame()
            theme_summary_df = pd.DataFrame()

            new_review_metrics = calculate_new_review_metrics(
                new_reviews_df
            )

            emerging_alerts = []

            retailer_update = (
                f"{source}: Review processing was not completed."
            )
                
            st.warning(
                f"{source} reviews were scraped, but a later "
                "report-processing step failed."
            )

            st.code(str(error))

        new_reviews_by_source[source] = reporting_reviews_df
        theme_summaries[source] = theme_summary_df
        retailer_updates[source] = retailer_update

        st.info(retailer_update)

        if not reporting_reviews_df.empty:
            st.write("New review rating breakdown")

            metric_col1, metric_col2, metric_col3 = st.columns(3)

            with metric_col1:
                average_value = new_review_metrics[
                    "new_review_average_rating"
                ]

                st.metric(
                    "New Review Average",
                    (
                        f"{average_value:.2f}"
                        if average_value is not None
                        else "N/A"
                    )
                )

            with metric_col2:
                st.metric(
                    "5-Star New Reviews",
                    new_review_metrics[
                        "five_star_new_reviews"
                    ]
                )

            with metric_col3:
                low_rating_count = (
                    new_review_metrics[
                        "one_star_new_reviews"
                    ]
                    + new_review_metrics[
                        "two_star_new_reviews"
                    ]
                )

                st.metric(
                    "1-2 Star New Reviews",
                    low_rating_count
                )

            if emerging_alerts:
                st.warning(
                    "Potential emerging concerns: "
                    + ", ".join(
                        alert["theme"]
                        for alert in emerging_alerts
                    )
                )

        if not theme_summary_df.empty:
            with st.expander(
                f"{source} new-review themes"
            ):
                st.dataframe(
                    theme_summary_df,
                    use_container_width=True
                )

        retailer_data[source] = df
        retailer_links[source] = link

        results_summary.append({
            "Product": selected_product,
            "Source": source,
            "Status": "Complete",
            "Reviews": len(df),
            "Reviews in Selected Period": len(
                reporting_reviews_df
            ),
            "Current Rating": (
                round(current_rating, 2)
                if current_rating is not None
                else "N/A"
            ),
            "Rating Change": (
                f"{rating_change:+.2f}"
                if rating_change is not None
                else "N/A"
            )
        })

        if show_preview:
            st.subheader(
                f"{selected_product} — {source}"
            )

            st.dataframe(
                df.head(10),
                use_container_width=True
            )

        product_progress_bar.progress(
            index / len(links)
        )

    product_progress_text.write("Finished.")
    review_progress_text.empty()

    summary_df = pd.DataFrame(results_summary)

    st.success("Report generation complete.")

    st.dataframe(
        summary_df,
        use_container_width=True
    )

    if retailer_data:
        report_file = create_combined_excel_report(
            retailer_data=retailer_data,
            retailer_links=retailer_links,
            product_name=selected_product,
            new_reviews_by_source=new_reviews_by_source,
            theme_summaries=theme_summaries,
            retailer_updates=retailer_updates
        )

        safe_product_name = clean_filename(
            selected_product
        )

        st.download_button(
            label="Download Product Report",
            data=report_file,
            file_name=(
                f"{safe_product_name}"
                "_Retailer_Report.xlsx"
            ),
            mime=(
                "application/"
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True
        )

    else:
        st.warning(
            "No Excel file was created."
        )
st.divider()

with st.expander("Biweekly email preview"):
    st.caption(
        "This generates a formatted preview only. "
        "No email will be sent."
    )

    if report_all_time:
        st.info(
            "Turn off 'All time' and select a start "
            "and end date above to generate the preview."
        )

    else:
        st.write(
            f"Preview period: {report_start_date} "
            f"through {report_end_date}"
        )

        if st.button(
            "Generate biweekly preview",
            key="generate_biweekly_preview"
        ):
            try:
                with st.spinner(
                    "Generating report from Supabase..."
                ):
                    
                    report_preview = biweekly_email.build_biweekly_report(
                        start_date=report_start_date,
                        end_date=report_end_date
                    ) 

                st.success("Preview generated.")

                components.html(
                    report_preview,
                    height=4000,
                    scrolling=True
                )

            except Exception as error:
                st.error(
                    "The preview could not be generated. "
                    f"{type(error).__name__}: {error}"
                )
