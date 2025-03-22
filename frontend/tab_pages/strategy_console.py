import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.strategy_helper.client import get_strategy_metadata, get_strategy_logs
from frontend.src.library.ui_elements import col_style2
import pandas as pd
from frontend.src.library.strategy_helper.console_helper import real_time_strategy_plot, static_strategy_plot


fix_page_layout('strategy monitor')
set_page_title("Strategy Monitor")
# st.html(col_style2)
st.write("Monitor the progress of a running strategy or examine a finished one.")


strategies = get_strategy_metadata("all")
if strategies:

    st.html(
        "<h4 style='text-align: left;margin-top:0.1em; margin-bottom:0.1em; padding:0;color:#5E5E5E'>Strategies</h4>")
    df = pd.DataFrame(strategies)
    df['created_at'] = pd.to_datetime(df['created_at'], unit='ms')
    df['monitor'] = False
    df.insert(0, 'monitor', df.pop('monitor'))
    st.caption("Use the ***search bar*** on the top right of the table to search for specific **keywords**")
    edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows='fixed', disabled=["strategy_id", "symbol", "quote_amount", "time_interval", "trades_limit", "strategy_name", "created_at", "status"])
    st.info("💡 The **DateTime** above refers to the **UTC** timestamp. So times may be different from your local time.")
    df_to_show = edited_df.loc[edited_df["monitor"] == True].copy().reset_index(drop=True)


    # st.dataframe(df, use_container_width=True, hide_index=True)

    if df_to_show.shape[0] == 0:
        pass
    elif df_to_show.shape[0] == 1:
        st.divider()
        strategy_id = df_to_show["strategy_id"].iloc[0]
        st.html(f"<h3 style='text-align: left;margin-top:0.1em; margin-bottom:0.1em; padding:0;color:#5E5E5E'>Strategy {strategy_id} Overview</h3>")

        # Get Logs Data
        logs = get_strategy_logs(strategy_id)
        logs_df = pd.DataFrame(logs)

        if logs_df is not None:

            # Stop, Pause Strategy
            status_change_options = True if df_to_show["status"].iloc[0] == "inactive" else False
            col0, col1 = st.columns(2)
            with col0:
                st.button("Pause Strategy", type="secondary", icon=":material/pause_circle:", disabled=status_change_options)
            with col1:
                st.button("Stop Strategy", type="primary", icon=":material/cancel:", disabled=status_change_options)


            if status_change_options:
                st.sidebar.download_button(
                    "Download to CSV",
                    logs_df.to_csv(index=False).encode('utf-8'),
                    f"{strategy_id}.csv",
                    "text/csv",
                    key='download-csv',
                    use_container_width=True,
                    icon=":material/download:"
                )

            logs_df['timestamp'] = pd.to_datetime(logs_df['timestamp'], unit='ms')
            show_table = st.toggle("Show Logs Table", value=False)
            if show_table:
                st.dataframe(logs_df, use_container_width=True, hide_index=True)


            real_time_option = st.toggle("Real Time Monitor Line Plot", value=True, disabled=status_change_options)
            if real_time_option:
                real_time_strategy_plot(logs_df[["timestamp", "price", "order"]], strategy_id)
            else:
                st.html(
                    "<h4 style='text-align: left;margin-top:0.1em; margin-bottom:0.1em; padding:0;color:#5E5E5E'>Strategy Logs Lineplot</h4>")
                static_strategy_plot(logs_df[["timestamp", "price", "order"]])

        else:
            st.warning("Failed to load Strategy Logs", icon=":material/warning:")
    else:
        st.warning("Only one strategy at a time can be monitored.", icon=":material/warning:")

else:
    html_content = """
    <div style="text-align: center; color: #5E5E5E; font-weight: bold; font-size: 24px;">
        <br>
        No Strategies found.
        <br>
    </div>
    """
    st.html(html_content)
