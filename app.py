import streamlit as st

st.set_page_config(page_title="Beauty Review Tracker", layout="wide")

st.title("Beauty Review Tracker")
st.write("Track reviews and ratings across Ulta, Sephora, and brand websites.")

brand_name = st.text_input("Brand name")
product_urls = st.text_area("Product URLs", placeholder="Paste one URL per line")

sources = st.multiselect(
    "Sources",
    ["Ulta", "Sephora", "Brand Website"],
    default=["Ulta"]
)

if st.button("Collect Reviews"):
    st.info("Review collection will be added next.")
