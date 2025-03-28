import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.strategy_helper.client import get_strategy_metadata, get_strategy_logs, stop_strategy
import pandas as pd
from frontend.src.library.strategy_helper.console_helper import real_time_strategy_plot, static_strategy_plot, show_evaluation_metrics, show_active_strategy_count, strategy_plot_info, strategy_info_card


fix_page_layout('strategy monitor')
set_page_title("Strategy Monitor")
st.write("Monitor the progress of a running strategy or examine a finished one.")


strategies = get_strategy_metadata("all")
if strategies:

    st.html(
        "<h4 style='text-align: left;margin-top:0.1em; margin-bottom:0.1em; padding:0;color:#5E5E5E'>Strategies</h4>")
    df = pd.DataFrame(strategies)
    show_active_strategy_count(df[df["status"]=="active"].shape[0], df.shape[0])
    df['created_at'] = pd.to_datetime(df['created_at'], unit='ms')
    df['monitor'] = False
    df.insert(0, 'monitor', df.pop('monitor'))
    st.caption("Use the ***search bar*** on the top right of the table to search for specific **keywords**")
    edited_df = st.data_editor(df.sort_values(by='created_at', ascending=False), use_container_width=True, hide_index=True, num_rows='fixed', disabled=["strategy_id", "symbol", "quote_amount", "time_interval", "trades_limit", "strategy_name", "created_at", "status"])
    st.info("💡 The **DateTime** above refers to the **UTC** timestamp. So times may be different from your local time.")
    df_to_show = edited_df.loc[edited_df["monitor"] == True].copy().reset_index(drop=True)


    # st.dataframe(df, use_container_width=True, hide_index=True)
    if df_to_show.shape[0] == 0:
        pass
    elif df_to_show.shape[0] == 1:
        st.divider()
        strategy_id = df_to_show["strategy_id"].iloc[0]


        strategy_info_card(strategy_id=strategy_id, symbol=df_to_show["symbol"].iloc[0], balance=df_to_show["quote_amount"].iloc[0], time_interval=df_to_show["time_interval"].iloc[0], trades_limit= df_to_show["trades_limit"].iloc[0],
                               strategy_name=df_to_show["strategy_name"].iloc[0], created_at=df_to_show["created_at"].iloc[0].strftime("%Y-%m-%d %H:%M:%S"), status=df_to_show["status"].iloc[0])
        # Get Logs Data
        logs = get_strategy_logs(strategy_id)
        if logs is not None and len(logs) > 0:

            logs_df = pd.DataFrame(logs)
            # Stop, Pause Strategy
            status_change_options = True if df_to_show["status"].iloc[0] == "inactive" else False
            col0, col1 = st.columns(2, gap="small")
            with col0:
                if st.button("Stop Strategy", type="primary", icon=":material/cancel:", disabled=status_change_options):
                    with st.spinner("Stopping Strategy"):
                        st.toast("Stopping Strategy...", icon=":material/cancel:")
                        stop_strategy(strategy_id)
                        st.rerun()
            with col1:
                st.button("Pause Strategy", type="secondary", icon=":material/pause_circle:", disabled=status_change_options)


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

            st.divider()
            st.html(
                "<h3 style='text-align: left;margin-top:0.1em; margin-bottom:0.1em; padding:0;color:#5E5E5E'>1. Strategy Logs Table</h3>")
            logs_df['timestamp'] = pd.to_datetime(logs_df['timestamp'], unit='ms')
            st.caption("The strategy logs ***order*** field contains the action the algorithm too at a specific timestamp. "
                       "These actions are **HOLD** if no action is taken, **BUY** and **SELL**. If the BUY or SELL orders fail"
                       " due to an error or other condition is is denoted as **INVALID_BUY** and **INVALID_SELL**.")

            hide_table = st.toggle("hide table", value=False)
            if not hide_table:
                st.dataframe(logs_df, use_container_width=True, hide_index=True)

            st.divider()

            st.html("<h3 style='text-align: left;margin-top:0.1em; margin-bottom:0.1em; padding:0;color:#5E5E5E'>2. Strategy Evaluation Metrics</h3>")
            show_evaluation_metrics(strategy_id)

            st.divider()
            st.html(
                "<h3 style='text-align: left;margin-top:0.1em; margin-bottom:0.1em; padding:0;color:#5E5E5E'>3. Strategy Logs Plot</h3>")
            strategy_plot_info()

            real_time_option = st.toggle("Real Time Monitor Line Plot", value=False, disabled=status_change_options)
            hide_invalid = st.toggle("hide invalid orders", value=False)
            if real_time_option:
                real_time_strategy_plot(logs_df[["timestamp", "price", "order"]], strategy_id, df_to_show["time_interval"].iloc[0], hide_invalid)
            else:
                static_strategy_plot(logs_df[["timestamp", "price", "order"]], hide_invalid)

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
