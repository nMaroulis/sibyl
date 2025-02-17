import pandas as pd
import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout
from frontend.src.library.history_helper.funcs import sidebar_update_history, trading_history_table, get_status_barplot, get_trading_history_line_plot


fix_page_layout('Report')
st.html("<h2 style='text-align: center;margin-top:0; padding-top:0;'>Trading Report</h2>")

strat_status = st.sidebar.radio('Deployed Strategy History Status:', options=['all', 'active', 'completed', 'partially_completed', 'cancelled'], index=0)
sidebar_update_history()
st.sidebar.selectbox('Exchange', options=['All', 'Binance'], disabled=True)

df = trading_history_table(strat_status)

if df is None:
    st.error('📶 Something went wrong while fetching the Trading History. Check server Connection.')
else:
    th_tab, vs_tab = st.tabs(['Trading History', 'Visual Inspection'])
    with th_tab:
        st.html("<h5 style='text-align: left;margin-top:0; padding-top:0;'>Trading History Table</h5>")
        df['show_plot'] = False
        df.insert(0, 'Status', df.pop('Status'))
        df.insert(0, 'show_plot', df.pop('show_plot'))

        edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows='fixed', disabled=['Exchange', 'DateTime', 'buy_orderId', 'from_asset', 'to_asset', 'from_amount','quantity_bought', 'from_price', 'DateTime [Sell]', 'sell_orderId', 'price_to_sell', 'Order Type', 'Strategy', 'Status'])
        st.info("💡 The **DateTime** above refers to the **UTC** timestamp. So times may be different than your local time.")

        df_to_plot = edited_df.loc[edited_df["show_plot"] == True].copy().reset_index(drop=True)
        if df_to_plot.shape[0] > 0:
            with st.spinner("Generating Trade History Plot..."):
                #try:
                fig = get_trading_history_line_plot(df_to_plot)  # & (edited_df["show_plot"] == True)
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                # except Exception as e:
                #     st.error("Failed to generate the Trade History Plot. Error message : {}".format(e))
    with vs_tab:
        st.html("<h5 style='text-align: left;margin-top:0; padding-top:0;'>Trading History Bar Plot</h5>")
        get_status_barplot(df['Status'])
