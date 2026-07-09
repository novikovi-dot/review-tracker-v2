import streamlit as st
import pandas as pd
import zipfile
from io import BytesIO

from scrapers.ulta import (
    scrape_product as scrape_ulta_product,
    create_excel_file,
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

    elif source == "Sephora":
        return scrape_sephora_product(
            link,
            delay_seconds,
            review_progress_bar,
            review_progress_text
       )

    elif source == "Brand Website":
        return scrape_brand_product(
            link,
            delay_seconds,
            review_progress_bar,
            review_progress_text
       )

    else:
        st.error("Unknown source selected.")
        return None


check_password()

st.title("⭐ Beauty Review Tracker")
st.write("Paste one or more product links below. One link per line.")

source = st.selectbox(
    "Source",
    ["Ulta", "Sephora", "Brand Website"]
)

placeholder_by_source = {
    "Ulta": "https://www.ulta.com/p/...",
    "Sephora": "https://www.sephora.com/product/...",
    "Brand Website": "https://olehenriksen.com/products/..."
}

product_links_text = st.text_area(
    "Product links",
    height=160,
    placeholder=placeholder_by_source[source]
)

with st.expander("Settings"):
    delay_seconds = st.slider(
        "Delay between requests",
        min_value=0.1,
        max_value=2.0,
        value=0.25,
        step=0.05
    )

    show_preview = st.checkbox("Show preview table", value=True)


if st.button("Scrape Reviews", use_container_width=True):
    links = [link.strip() for link in product_links_text.splitlines() if link.strip()]

    if not links:
        st.error("Please paste at least one product link.")
        st.stop()

    all_excel_files = []

    product_progress_bar = st.progress(0)
    product_progress_text = st.empty()
    review_progress_bar = st.progress(0)
    review_progress_text = st.empty()

    results_summary = []

    for index, link in enumerate(links, start=1):
        product_progress_text.write(f"Product {index} of {len(links)}")
        product_progress_bar.progress((index - 1) / len(links))

        review_progress_bar.progress(0)
        review_progress_text.write("Finding reviews...")

        product_name = clean_filename(link)

        df = scrape_selected_source(
            source,
            link,
            delay_seconds,
            review_progress_bar,
            review_progress_text
        )

        if df is None or df.empty:
            results_summary.append({
                "Product": product_name,
                "Source": source,
                "Status": "No reviews found",
                "Reviews": 0,
                "New Saved": 0
            })
            continue

        if "review_id" in df.columns:
            df = df.drop_duplicates(subset=["review_id"])
        else:
            df = df.drop_duplicates()

        saved_count = save_reviews(
            df=df,
            source=source,
            product_name=product_name,
            product_url=link
        )

        excel_file = create_excel_file(df)
        file_name = f"{product_name}.xlsx"

        all_excel_files.append((file_name, excel_file))

        results_summary.append({
            "Product": product_name,
            "Source": source,
            "Status": "Complete",
            "Reviews": len(df),
            "New Saved": saved_count
        })

        if show_preview:
            st.subheader(product_name)
            st.dataframe(df.head(10))

        product_progress_bar.progress(index / len(links))

    product_progress_text.write("Finished.")
    review_progress_text.empty()

    summary_df = pd.DataFrame(results_summary)

    st.success("Scraping complete.")
    st.dataframe(summary_df)

    if len(all_excel_files) == 1:
        file_name, excel_file = all_excel_files[0]

        st.download_button(
            label="Download Excel File",
            data=excel_file,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    elif len(all_excel_files) > 1:
        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for file_name, excel_file in all_excel_files:
                zip_file.writestr(file_name, excel_file.getvalue())

        zip_buffer.seek(0)

        st.download_button(
            label="Download ZIP File",
            data=zip_buffer,
            file_name="review_exports.zip",
            mime="application/zip",
            use_container_width=True
        )

    else:
        st.warning("No Excel files were created.")
