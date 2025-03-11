import pandas as pd
import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.history_helper.funcs import sidebar_update_history, trading_history_table, get_status_barplot, get_trading_history_line_plot, trade_history_instructions


fix_page_layout('Report')
set_page_title("Trading Report")
# strat_status = st.sidebar.radio('Deployed Strategy History Status:', options=['all', 'active', 'completed', 'partially_completed', 'cancelled'], index=0)
sidebar_update_history()
st.sidebar.selectbox('Exchange', options=['All', 'Binance'], disabled=True)

df = trading_history_table()

if df is None:
    st.error('📶 Something went wrong while fetching the Trading History. Check server Connection.')
else:
    th_tab, vs_tab = st.tabs(['Trading History', 'Visual Inspection'])
    with th_tab:
        st.html("<h4 style='text-align: left;margin-top:0.1em; margin-bottom:0.1em; padding:0;color:#5E5E5E'>Trading History Table</h4>")
        trade_history_instructions()
        df['show_plot'] = False
        df.insert(0, 'show_plot', df.pop('show_plot'))
        st.caption("Use the ***search bar*** on the top right of the table to search for specific **keywords**")
        edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows='fixed',
                                   disabled=['Exchange', 'DateTime', 'Order Id', 'Quote Asset', 'Base Asset', 'Base Quantity',
                                            'Quote Quantity', 'Side', 'Type', 'Status', 'TiF', 'Commission', 'Commission Asset', 'STPM'])
        st.info("💡 The **DateTime** above refers to the **UTC** timestamp. So times may be different from your local time.")
        df_to_plot = edited_df.loc[edited_df["show_plot"] == True].copy().reset_index(drop=True)
        if df_to_plot.shape[0] > 0:
            with st.spinner("Generating Trade History Plot..."):
                fig = get_trading_history_line_plot(df_to_plot)
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    with vs_tab:
        st.html("<h5 style='text-align: left;margin-top:0; padding-top:0;'>Trading History Bar Plot</h5>")
        get_status_barplot(df['Status'])
