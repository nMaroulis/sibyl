import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.strategy_helper.client import get_strategy_metadata, get_strategy_logs
from frontend.src.library.ui_elements import col_style2
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from frontend.src.library.strategy_helper.console_helper import real_time_strategy_plot


fix_page_layout('strategy monitor')
set_page_title("Strategy Monitor")
# st.html(col_style2)

html_content = """
<div style="text-align: center; color: red; font-weight: bold; font-size: 24px;">
    <br>
    UNDER DEVELOPMENT.
    <br>
</div>
"""
st.html(html_content)


strategies = get_strategy_metadata("all")
if strategies:

    st.button("Pause Strategy", type="secondary", icon=":material/pause_circle:", disabled=True)
    st.button("Stop Strategy", type="primary", icon=":material/cancel:")

    df = pd.DataFrame(strategies)
    df['created_at'] = pd.to_datetime(df['created_at'], unit='ms')

    df['monitor'] = False
    df.insert(0, 'monitor', df.pop('monitor'))
    st.caption("Use the ***search bar*** on the top right of the table to search for specific **keywords**")
    edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows='fixed')
    st.info("💡 The **DateTime** above refers to the **UTC** timestamp. So times may be different from your local time.")
    df_to_show = edited_df.loc[edited_df["monitor"] == True].copy().reset_index(drop=True)


    # st.dataframe(df, use_container_width=True, hide_index=True)


    if df_to_show.shape[0] > 0:
        st.write(df_to_show["strategy_id"].iloc[0])
        logs = get_strategy_logs(df_to_show["strategy_id"].iloc[0])
        logs_df = pd.DataFrame(logs)
        st.write(logs_df)
        logs_df['timestamp'] = pd.to_datetime(logs_df['timestamp'], unit='ms')
        st.dataframe(logs_df, use_container_width=True, hide_index=True)


        # Plotting
        fig, ax = plt.subplots(figsize=(10, 6))

        # Plot the price as a line
        ax.plot(logs_df['timestamp'], logs_df['price'], label='Price', color='blue')

        # Add markers for BUY and SELL actions
        for i, row in logs_df.iterrows():
            if row['order'] == 'BUY':
                ax.plot(row['timestamp'], row['price'], marker='o', markersize=10, color='green', label='BUY' if i == 0 else "")
            elif row['order'] == 'SELL':
                ax.plot(row['timestamp'], row['price'], marker='o', markersize=10, color='red', label='SELL' if i == 0 else "")

        # Set labels and title
        ax.set_xlabel('Timestamp')
        ax.set_ylabel('Price')
        ax.set_title('Price vs Timestamp with BUY/SELL orders')

        # Format the x-axis with date
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

        # Rotate x labels for better readability
        plt.xticks(rotation=45)

        # Show legend
        ax.legend()

        # Show the plot in Streamlit
        st.pyplot(fig)


    real_time_option = st.toggle("Real Time Monitor", value=False)
    if real_time_option:
        real_time_strategy_plot()

else:
    html_content = """
    <div style="text-align: center; color: #5E5E5E; font-weight: bold; font-size: 24px;">
        <br>
        No Strategies found.
        <br>
    </div>
    """
    st.html(html_content)
