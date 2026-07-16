import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date, timedelta

from products import PRODUCTS

from scrapers.ulta import (
    scrape_product as scrape_ulta_product,
    clean_filename
)

from analytics.theme_analysis import (
    analyze_themes,
    build_retailer_update,
    calculate_new_review_metrics,
    get_emerging_issue_alerts
)

from database.db import (
    save_reviews,
    save_snapshot,
    get_snapshot_changes,
    load_reviews_by_date_range
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

    default_end_date = date.today()
    default_start_date = (
        default_end_date - timedelta(days=13)
    )

    st.write("Review reporting period")

    date_col1, date_col2 = st.columns(2)

    with date_col1:
        report_start_date = st.date_input(
            "Start date",
            value=default_start_date,
            max_value=default_end_date
        )

    with date_col2:
        report_end_date = st.date_input(
            "End date",
            value=default_end_date,
            max_value=default_end_date
        )

if report_start_date > report_end_date:
    st.error(
        "The start date cannot be later than the end date."
    )
    st.stop()

    default_end_date = date.today()
    default_start_date = (
        default_end_date - timedelta(days=13)
    )

    date_col1, date_col2 = st.columns(2)

    with date_col1:
        report_start_date = st.date_input(
            "Review start date",
            value=default_start_date
        )

    with date_col2:
        report_end_date = st.date_input(
            "Review end date",
            value=default_end_date
        )

if report_start_date > report_end_date:
    st.error(
        "The review start date must be before "
        "the review end date."
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

        if df is None or df.empty:
            results_summary.append({
                "Product": selected_product,
                "Source": source,
                "Status": "No reviews found",
                "Reviews": 0,
                "New Reviews": 0
            })
            continue

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

        retailer_update = (
            f"{source}: No update was generated."
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

            reporting_reviews_df = load_reviews_by_date_range(
                product_name=selected_product,
                source=source,
                start_date=report_start_date,
                end_date=report_end_date
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

            new_review_metrics = calculate_new_review_metrics(
                reporting_reviews_df
            )

            theme_summary_df = analyze_themes(
                reporting_reviews_df
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

        except Exception as error:
            saved_count = 0
            new_reviews_df = pd.DataFrame()
            theme_summary_df = pd.DataFrame()

            new_review_metrics = calculate_new_review_metrics(
                new_reviews_df
            )

            emerging_alerts = []

            retailer_update = (
                f"{source}: Review analysis was not "
                "created because database saving failed."
            )

            st.warning(
                f"{source} reviews were scraped "
                "successfully, but database saving failed."
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
            "Reviews in Selected Period": len(reporting_reviews_df)
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
