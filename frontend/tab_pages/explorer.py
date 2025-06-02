import streamlit as st
from frontend.src.utils.explorer_helper.client import fetch_blocks
from frontend.src.utils.explorer_helper.plots import plot_block_height_weight_tx_count
from frontend.src.utils.ui_elements import fix_page_layout, set_page_title
from frontend.src.utils.oracle.ui_elements import oracle_button


fix_page_layout('🧭 explorer')
set_page_title("Blockchain Explorer")
st.write("The **Explorer** 🧭 module has access to APIs that explore blockchain data.")


def show_blockchain_statistics(data):
    st.subheader("Statistics")
    st.write("Summary statistics of the data:")
    st.write(data.describe())


with st.form("explorer_form"):
    blockchains = ["Bitcoin (BTC)", "Litecoin (LTC)"]

    c0, c1 = st.columns([2, 1])
    with c0:
        selected_blockchain = st.selectbox("Choose a blockchain", blockchains)
    with c1:
        block_count = st.number_input('Block count', min_value=1, max_value=10000, value=50)

    sub_button = st.form_submit_button("Explore 🧭")
    if sub_button:
        data = fetch_blocks(selected_blockchain, block_count)
        if data is not None:
            st.caption("For **Bitcoin** the explorer checks the https://blockstream.info/ API. Block weight in KBs.")
            st.dataframe(data, use_container_width=True)
            if selected_blockchain == "Bitcoin (BTC)":
                plot_block_height_weight_tx_count(data)
        else:
            st.warning("Failed to fetch Blockchain data...", icon=":material/warning:")

oracle_button(module="explorer", enabled=False)