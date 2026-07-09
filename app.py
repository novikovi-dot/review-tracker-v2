import streamlit as st
import pandas as pd
from io import BytesIO

from products import PRODUCTS

from scrapers.ulta import (
    scrape_product as scrape_ulta_product,
    clean_filename
)

from scrapers.sephora import scrape_sephora_product
from scrapers.brand import scrape_brand_product


def save_reviews(df, source, product_name, product_url):
    return 0


st.set_page_config(page_title="Beauty Review Tracker", page_icon="⭐", layout="centered")

APP_PASSWORD = "abc"


def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 Beauty Review Tracker")
        password = st.text_input("Enter password:", type="password")

        if st.button("Login"):
            if password == APP_PASSWORD:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")

        st.stop()


def scrape_selected_source(source, link, delay_seconds, review_progress_bar, review_progress_text):
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


def summarize_retailer(df, source, product_name, product_url):
    rating_col = get_rating_column(df)

    if rating_col:
        ratings = pd.to_numeric(df[rating_col], errors="coerce")
        avg_rating = round(ratings.mean(), 2) if ratings.notna().any() else ""
        five_star = int((ratings == 5).sum())
        four_star = int((ratings == 4).sum())
        three_star = int((ratings == 3).sum())
        two_star = int((ratings == 2).sum())
        one_star = int((ratings == 1).sum())
    else:
        avg_rating = ""
        five_star = four_star = three_star = two_star = one_star = 0

    recommended_rate = ""
    
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
        return pd.DataFrame(columns=["Rating", "Review Count", "Percentage"])

    ratings = pd.to_numeric(df[rating_col], errors="coerce")

    breakdown = (
        ratings
        .value_counts()
        .sort_index(ascending=False)
        .reset_index()
    )

    breakdown.columns = ["Rating", "Review Count"]

    if len(df) > 0:
        breakdown["Percentage"] = breakdown["Review Count"] / len(df)

    return breakdown


def create_combined_excel_report(retailer_data, retailer_links, product_name):
    output = BytesIO()

    comparison_rows = []

    for source, df in retailer_data.items():
        rating_col = get_rating_column(df)

        if rating_col:
            ratings = pd.to_numeric(df[rating_col], errors="coerce")
            avg_rating = round(ratings.mean(), 2) if ratings.notna().any() else ""
        else:
            avg_rating = ""

        comparison_rows.append({
            "Product": product_name,
            "Retailer": source,
            "Reviews": len(df),
            "Average Rating": avg_rating,
            "Product URL": retailer_links.get(source, "")
        })

    comparison_df = pd.DataFrame(comparison_rows)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        comparison_df.to_excel(writer, index=False, sheet_name="Retailer Comparison")

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

            summary_df.to_excel(writer, index=False, sheet_name=summary_sheet)
            rating_breakdown_df.to_excel(writer, index=False, sheet_name=ratings_sheet)
            df.to_excel(writer, index=False, sheet_name=reviews_sheet)

        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions

            for column_cells in worksheet.columns:
                max_length = 0
                column_letter = column_cells[0].column_letter

                for cell in column_cells:
                    if cell.value is not None:
                        max_length = max(max_length, len(str(cell.value)))

                    cell.alignment = cell.alignment.copy(
                        wrap_text=True,
                        vertical="top"
                    )

                worksheet.column_dimensions[column_letter].width = min(max_length + 2, 70)

    output.seek(0)
    return output


check_password()

st.title("⭐ Beauty Review Tracker")
st.write("Select a product and choose which retailer platforms to include.")

product_names = list(PRODUCTS.keys())

selected_product = st.selectbox(
    "Product",
    product_names
)

product_info = PRODUCTS[selected_product]

platforms = ["Ulta", "Sephora", "Brand Website"]

for platform in platforms:
    key = f"platform_{platform}"
    if key not in st.session_state:
        st.session_state[key] = True

button_col1, button_col2 = st.columns(2)

with button_col1:
    if st.button("Select All", use_container_width=True):
        for platform in platforms:
            st.session_state[f"platform_{platform}"] = True
        st.rerun()

with button_col2:
    if st.button("Clear All", use_container_width=True):
        for platform in platforms:
            st.session_state[f"platform_{platform}"] = False
        st.rerun()

st.write("Platforms")

col1, col2, col3 = st.columns(3)

with col1:
    st.checkbox("Ulta", key="platform_Ulta")

with col2:
    st.checkbox("Sephora", key="platform_Sephora")

with col3:
    st.checkbox("Brand Website", key="platform_Brand Website")

selected_platforms = [
    platform for platform in platforms
    if st.session_state[f"platform_{platform}"]
]

with st.expander("Selected product links"):
    for platform in platforms:
        link = product_info.get(platform, "")
        if link:
            st.write(f"**{platform}:** {link}")
        else:
            st.write(f"**{platform}:** No link saved")

with st.expander("Settings"):
    delay_seconds = st.slider(
        "Delay between requests",
        min_value=0.1,
        max_value=2.0,
        value=0.25,
        step=0.05
    )

    show_preview = st.checkbox("Show preview table", value=True)


if st.button("Generate Product Report", use_container_width=True):
    links = []

    for platform in selected_platforms:
        link = product_info.get(platform)

        if link:
            links.append((platform, link))

    if not links:
        st.error("Please select at least one platform with a saved link.")
        st.stop()

    product_progress_bar = st.progress(0)
    product_progress_text = st.empty()
    review_progress_bar = st.progress(0)
    review_progress_text = st.empty()

    results_summary = []
    retailer_data = {}
    retailer_links = {}

    for index, (source, link) in enumerate(links, start=1):
        product_progress_text.write(f"Platform {index} of {len(links)}: {source}")
        product_progress_bar.progress((index - 1) / len(links))

        review_progress_bar.progress(0)
        review_progress_text.write("Finding reviews...")

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
                "Reviews": 0
            })
            continue

        if "review_id" in df.columns:
            df = df.drop_duplicates(subset=["review_id"])
        else:
            df = df.drop_duplicates()

        save_reviews(
            df=df,
            source=source,
            product_name=selected_product,
            product_url=link
        )

        retailer_data[source] = df
        retailer_links[source] = link

        results_summary.append({
            "Product": selected_product,
            "Source": source,
            "Status": "Complete",
            "Reviews": len(df)
        })

        if show_preview:
            st.subheader(f"{selected_product} — {source}")
            st.dataframe(df.head(10))

        product_progress_bar.progress(index / len(links))

    product_progress_text.write("Finished.")
    review_progress_text.empty()

    summary_df = pd.DataFrame(results_summary)

    st.success("Report generation complete.")
    st.dataframe(summary_df)

    if retailer_data:
        report_file = create_combined_excel_report(
            retailer_data=retailer_data,
            retailer_links=retailer_links,
            product_name=selected_product
        )

        safe_product_name = clean_filename(selected_product)

        st.download_button(
            label="Download Product Report",
            data=report_file,
            file_name=f"{safe_product_name}_Retailer_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    else:
        st.warning("No Excel file was created.")
