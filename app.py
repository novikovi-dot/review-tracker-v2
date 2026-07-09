import streamlit as st
import pandas as pd
import zipfile
from io import BytesIO

from products import PRODUCTS

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
st.write("Select a product and choose which retailer platforms to include.")

product_names = list(PRODUCTS.keys())

selected_product = st.selectbox(
    "Product",
    product_names
)

selected_platforms = st.multiselect(
    "Platforms",
    ["Ulta", "Sephora", "Brand Website"],
    default=["Ulta", "Sephora", "Brand Website"]
)

product_info = PRODUCTS[selected_product]

with st.expander("Selected product links"):
    for platform in ["Ulta", "Sephora", "Brand Website"]:
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


if st.button("Generate Report", use_container_width=True):
    links = []

    for platform in selected_platforms:
        link = product_info.get(platform)

        if link:
            links.append((platform, link))

    if not links:
        st.error("Please select at least one platform with a saved link.")
        st.stop()

    all_excel_files = []

    product_progress_bar = st.progress(0)
    product_progress_text = st.empty()
    review_progress_bar = st.progress(0)
    review_progress_text = st.empty()

    results_summary = []

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
            product_name=selected_product,
            product_url=link
        )

        excel_file = create_excel_file(df)
        safe_product_name = clean_filename(selected_product)
        safe_source_name = clean_filename(source)

        file_name = f"{safe_product_name}_{safe_source_name}.xlsx"

        all_excel_files.append((file_name, excel_file))

        results_summary.append({
            "Product": selected_product,
            "Source": source,
            "Status": "Complete",
            "Reviews": len(df),
            "New Saved": saved_count
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

        safe_product_name = clean_filename(selected_product)

        st.download_button(
            label="Download ZIP File",
            data=zip_buffer,
            file_name=f"{safe_product_name}_retailer_reports.zip",
            mime="application/zip",
            use_container_width=True
        )

    else:
        st.warning("No Excel files were created.")
