import streamlit as st
import time
import plotly.graph_objs as go
import numpy as np
import pandas as pd
from frontend.src.library.strategy_helper.client import get_strategy_logs, get_strategy_evaluation


# Function to generate a random initial DataFrame
def generate_random_df(size=50):
    timestamps = np.arange(size)
    prices = np.cumsum(np.random.randn(size)) + 100  # Simulated price movement
    orders = np.random.choice(["BUY", "SELL", "HOLD"], size=size)
    return pd.DataFrame({"timestamp": timestamps, "price": prices, "order": orders})

def update_logs(strategy_id: str, last_timestamp: int):

    logs = get_strategy_logs(strategy_id, last_timestamp)  # df_to_show["strategy_id"].iloc[0])
    if logs is None or len(logs) == 0:
        return None

    logs_df = pd.DataFrame(logs)
    logs_df['timestamp'] = pd.to_datetime(logs_df['timestamp'], unit='ms')
    return logs_df


@st.fragment()
def real_time_strategy_plot(df: pd.DataFrame, strategy_id: str):
    # Create a placeholder for the Plotly chart
    chart = st.empty()
    # Initialize figure
    fig = go.Figure()

    # Add initial traces
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["price"], mode='lines', name='Price'))
    fig.add_trace(go.Scatter(x=df[df["order"] == "BUY"]["timestamp"], y=df[df["order"] == "BUY"]["price"], mode='markers', marker=dict(color='green', size=10), name='BUY'))
    fig.add_trace(go.Scatter(x=df[df["order"] == "SELL"]["timestamp"], y=df[df["order"] == "SELL"]["price"], mode='markers', marker=dict(color='red', size=10), name='SELL'))

    # Display the empty chart
    chart.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # Real-time update loop
    while True:
        upd_logs = update_logs(strategy_id, int(df['timestamp'].iloc[-1].timestamp() * 1000))
        if upd_logs is not None:
            df = pd.concat([df, upd_logs])
            with fig.batch_update():
                fig.data[0].x = df["timestamp"]  # Price line
                fig.data[0].y = df["price"]

                # Update BUY markers
                fig.data[1].x = df[df["order"] == "BUY"]["timestamp"]
                fig.data[1].y = df[df["order"] == "BUY"]["price"]

                # Update SELL markers
                fig.data[2].x = df[df["order"] == "SELL"]["timestamp"]
                fig.data[2].y = df[df["order"] == "SELL"]["price"]
            chart.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})


        time.sleep(5)
    # for i in range(len(df)):  # Go through the DataFrame row by row
    #     row = df.iloc[i]
    #
    #     # Append data
    #     with fig.batch_update():
    #         fig.data[0].x = df["timestamp"][:i+1]  # Price line
    #         fig.data[0].y = df["price"][:i+1]
    #
    #         # Update BUY markers
    #         fig.data[1].x = df[:i+1][df["order"] == "BUY"]["timestamp"]
    #         fig.data[1].y = df[:i+1][df["order"] == "BUY"]["price"]
    #
    #         # Update SELL markers
    #         fig.data[2].x = df[:i+1][df["order"] == "SELL"]["timestamp"]
    #         fig.data[2].y = df[:i+1][df["order"] == "SELL"]["price"]
    #
    #     # Update chart
    #     chart.plotly_chart(fig, use_container_width=True)
    #
    #     # Simulate real-time delay
    #     time.sleep(2)


# Static plotting function
def static_strategy_plot(df: pd.DataFrame):

    fig = go.Figure()
    # Plot price line
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["price"], mode='lines', name='Price'))

    # Plot BUY markers
    buy_df = df[df["order"] == "BUY"]
    fig.add_trace(go.Scatter(
        x=buy_df["timestamp"],
        y=buy_df["price"],
        mode='markers',
        marker=dict(color='green', size=10, symbol=100),
        name='BUY'
    ))

    invalid_buy_df = df[df["order"] == "INVALID_BUY"]
    fig.add_trace(go.Scatter(
        x=invalid_buy_df["timestamp"],
        y=invalid_buy_df["price"],
        mode='markers',
        marker=dict(color='green', size=10, symbol=104),
        name='Invalid BUY'
    ))

    # Plot SELL markers
    sell_df = df[df["order"] == "SELL"]
    fig.add_trace(go.Scatter(
        x=sell_df["timestamp"],
        y=sell_df["price"],
        mode='markers',
        marker=dict(color='red', size=10, symbol=100),
        name='SELL'
    ))

    invalid_sell_df = df[df["order"] == "INVALID_SELL"]
    fig.add_trace(go.Scatter(
        x=invalid_sell_df["timestamp"],
        y=invalid_sell_df["price"],
        mode='markers',
        marker=dict(color='red', size=10, symbol=104),
        name='Invalid SELL'
    ))


    # Display chart
    st.plotly_chart(fig, use_container_width=True)


@st.fragment()
def show_evaluation_metrics(strategy_id: str) -> None:
    with st.popover("What are the metrics", icon=":material/contact_support:"):
        st.title("Trading Performance Metrics Explained")

        st.subheader("Total Profit")
        st.write("The overall profit or loss from all trades over the evaluation period.")
        st.latex(r"\text{Total Profit} = \sum (\text{Profit from each trade})")

        st.subheader("Sharpe Ratio")
        st.write(
            "A risk-adjusted return metric that compares the average returns to the standard deviation of returns.")
        st.latex(r"\text{Sharpe Ratio} = \frac{E[R] - R_f}{\sigma}")
        st.write("- (E[R]\) is the expected return")
        st.write("- (R_f\) is the risk-free rate")
        st.write("- (\sigma\) is the standard deviation of returns")

        st.subheader("Max Drawdown")
        st.write("The maximum observed loss from a peak to a trough before a new peak is attained.")
        st.latex(
            r"\text{Max Drawdown} = \max \left( \frac{\text{Peak Value} - \text{Trough Value}}{\text{Peak Value}} \right)")

        st.subheader("Win Rate")
        st.write("The percentage of trades that ended in profit.")
        st.latex(r"\text{Win Rate} = \left( \frac{\text{Winning Trades}}{\text{Total Trades}} \right) \times 100")

        st.subheader("Average Win")
        st.write("The average profit made on winning trades.")
        st.latex(
            r"\text{Average Win} = \frac{\text{Total Profit from Winning Trades}}{\text{Number of Winning Trades}}")

        st.subheader("Average Loss")
        st.write("The average loss incurred on losing trades.")
        st.latex(
            r"\text{Average Loss} = \frac{\text{Total Loss from Losing Trades}}{\text{Number of Losing Trades}}")

        st.subheader("Sortino Ratio")
        st.write("A variation of the Sharpe Ratio that only considers downside risk.")
        st.latex(r"\text{Sortino Ratio} = \frac{E[R] - R_f}{\sigma_d}")
        st.write("- (\sigma_d\) is the standard deviation of negative returns.")

        st.subheader("Calmar Ratio")
        st.write("A risk-adjusted return metric that compares the annualized return to the maximum drawdown.")
        st.latex(r"\text{Calmar Ratio} = \frac{\text{Annualized Return}}{\text{Max Drawdown}}")

        st.subheader("Profit Factor")
        st.write("The ratio of total profits to total losses.")
        st.latex(r"\text{Profit Factor} = \frac{\text{Total Profit}}{\text{Total Loss}}")

        st.subheader("Number of Trades")
        st.write("The total count of trades executed.")
        st.latex(r"\text{Number of Trades} = \text{Winning Trades} + \text{Losing Trades}")

    html_txt = """
        <style>
        .evaluation-metrics-container {
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            background: rgba(255, 255, 255, 0.1);
            padding: 20px;
            border-radius: 12px;
            # box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(10px); /* Frosted glass effect */
            max-width: 100%;
        }

        .evaluation-metric {
            background: rgba(5, 122, 247, 1.0);
            color: white;
            padding: 12px 18px;
            border-radius: 10px;
            font-weight: bold;
            display: flex;
            align-items: center;
            gap: 8px;
            white-space: nowrap;
            transition: transform 0.2s, background 0.2s;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
        }
        
        .evaluation-metric:hover {
            background: rgba(1, 57, 117, 0.9);
            transform: scale(1.05);
        }

        .evaluation-metric-name {
            opacity: 0.9;
            font-size: 0.9em;
        }

        .evaluation-metric-value {
            font-size: 1.2em;
            font-weight: bold;
        }
        </style>"""

    strategy_evaluation = get_strategy_evaluation(strategy_id)
    if strategy_evaluation is None or len(strategy_evaluation['metrics']) == 0:
        st.warning("No evaluation metrics to show. No orders have been executed yet.", icon=":material/smart_toy:")
    else:
        html_txt += """<div class="evaluation-metrics-container">"""
        for key, value in strategy_evaluation["metrics"].items():
            html_txt += f"""<div class="evaluation-metric"><span class="evaluation-metric-name">{key}:</span> <span class="evaluation-metric-value">{value}</span></div>"""
        html_txt += """</div>"""
        st.html(html_txt)


        if st.button("Refresh Evaluation Metrics", icon=":material/update:", type="tertiary"):
            st.rerun()
