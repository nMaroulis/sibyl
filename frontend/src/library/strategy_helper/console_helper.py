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
def real_time_strategy_plot(df: pd.DataFrame, strategy_id: str, time_interval: str, show_invalid:bool):

    time_interval_dict = {'1s': 5, '15s': 15, '1m': 60, '5m': 300, '15m': 900,
                          '30m': 1800, '1h': 3600, '4h': 14400, '12h': 43200, '1d': 86400}
    time_interval = time_interval_dict[time_interval]

    # Create a placeholder for the Plotly chart
    chart = st.empty()
    # Initialize figure
    fig = go.Figure()

    # Add initial traces
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["price"], mode='lines', name='Price'))
    fig.add_trace(go.Scatter(x=df[df["order"] == "BUY"]["timestamp"], y=df[df["order"] == "BUY"]["price"], mode='markers', marker=dict(color='green', size=12, symbol='triangle-up'), name='BUY'))
    fig.add_trace(go.Scatter(x=df[df["order"] == "SELL"]["timestamp"], y=df[df["order"] == "SELL"]["price"], mode='markers', marker=dict(color='red', size=12, symbol='triangle-down'), name='SELL'))
    if show_invalid:
        fig.add_trace(go.Scatter(x=df[df["order"] == "INVALID_BUY"]["timestamp"], y=df[df["order"] == "INVALID_BUY"]["price"], mode='markers', marker=dict(color='green', size=10, symbol='triangle-up-open'), name='Invalid BUY'))
        fig.add_trace(go.Scatter(x=df[df["order"] == "INVALID_SELL"]["timestamp"], y=df[df["order"] == "INVALID_SELL"]["price"], mode='markers', marker=dict(color='red', size=10, symbol='triangle-down-open'), name='Invalid SELL'))

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

                if show_invalid:
                    # Update INVALID_BUY markers
                    fig.data[3].x = df[df["order"] == "INVALID_BUY"]["timestamp"]
                    fig.data[3].y = df[df["order"] == "INVALID_BUY"]["price"]

                    # Update INVALID_SELL markers
                    fig.data[4].x = df[df["order"] == "INVALID_SELL"]["timestamp"]
                    fig.data[4].y = df[df["order"] == "INVALID_SELL"]["price"]

            chart.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})


        progress_text = "Updating logs..."
        my_bar = st.progress(0, text=progress_text)
        for percent_complete in range(50):
            time.sleep(time_interval/50)
            my_bar.progress(percent_complete/50, text=progress_text)
        # time.sleep(1)
        my_bar.empty()

        # time.sleep(time_interval)


# Static plotting function
def static_strategy_plot(df: pd.DataFrame, show_invalid: bool, show_slippage: bool):

    fig = go.Figure()
    # Plot price line
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["price"], mode='lines', name='Price'))

    # Plot BUY markers
    buy_df = df[df["order"] == "BUY"]
    fig.add_trace(go.Scatter(
        x=buy_df["timestamp"],
        y=buy_df["price"],
        mode='markers',
        marker=dict(color='green', size=13, symbol='triangle-up'),
        name='BUY'
    ))


    # Plot SELL markers
    sell_df = df[df["order"] == "SELL"]
    fig.add_trace(go.Scatter(
        x=sell_df["timestamp"],
        y=sell_df["price"],
        mode='markers',
        marker=dict(color='red', size=13, symbol="triangle-down"), #  marker=dict(color='#ff0000', opacity=0.6,symbol="diamond", size=10, line=dict(color='#ae0000', width=2)),
        name='SELL'
    ))

    if show_slippage:
        executed_buy_df = buy_df.copy()
        executed_buy_df["executed_price"] = executed_buy_df["price"] - executed_buy_df["slippage"]

        executed_sell_df = sell_df.copy()
        executed_sell_df["executed_price"] = executed_sell_df["price"] - executed_sell_df["slippage"]

        # Show slippage as error bars
        fig.add_trace(go.Scatter(
            x=executed_buy_df["timestamp"],
            y=executed_buy_df["executed_price"],
            mode='markers',
            marker=dict(color='orange', size=10, symbol="star-triangle-up-open"),  # df["slippage"].apply(lambda x: 'blue' if x > 0 else ('orange' if x < 0 else 'gray'))
            name='Intended BUY Price'
        ))

        fig.add_trace(go.Scatter(
            x=executed_sell_df["timestamp"],
            y=executed_sell_df["executed_price"],
            mode='markers',
            marker=dict(color='purple', size=10, symbol="star-triangle-down-open"),
            name='Intended SELL Price'
        ))

        # Add lines to indicate slippage
        for _, row in executed_buy_df.iterrows():
            fig.add_trace(go.Scatter(
                x=[row["timestamp"], row["timestamp"]],
                y=[row["price"], row["executed_price"]],
                mode="lines",
                line=dict(color="orange", dash="dot"),
                showlegend=False
            ))

        for _, row in executed_sell_df.iterrows():
            fig.add_trace(go.Scatter(
                x=[row["timestamp"], row["timestamp"]],
                y=[row["price"], row["executed_price"]],
                mode="lines",
                line=dict(color="purple", dash="dot"),
                showlegend=False
            ))


    if show_invalid:
        invalid_buy_df = df[df["order"] == "INVALID_BUY"]
        fig.add_trace(go.Scatter(
            x=invalid_buy_df["timestamp"],
            y=invalid_buy_df["price"],
            mode='markers',
            marker=dict(color='green', size=10, symbol="triangle-up-open"),
            name='Invalid BUY'
        ))

        invalid_sell_df = df[df["order"] == "INVALID_SELL"]
        fig.add_trace(go.Scatter(
            x=invalid_sell_df["timestamp"],
            y=invalid_sell_df["price"],
            mode='markers',
            marker=dict(color='red', size=10, symbol="triangle-down-open"),
            name='Invalid SELL'
        ))

    # Display chart
    st.plotly_chart(fig, use_container_width=True)


@st.fragment()
def show_evaluation_metrics(strategy_id: str) -> None:
    with st.popover("What are the metrics", icon=":material/contact_support:"):
        st.subheader("Trading Performance Metrics Explained")

        st.subheader("Total Profit")
        st.write("The overall profit or loss from all trades over the evaluation period.")
        st.latex(r"\text{Total Profit} = \sum (\text{Profit from each trade})")

        st.subheader("Sharpe Ratio")
        st.write(
            "A risk-adjusted return metric that compares the average returns to the standard deviation of returns.")
        st.latex(r"\text{Sharpe Ratio} = \frac{E[R] - R_f}{\sigma}")
        st.write("- (E[R]) is the expected return")
        st.write("- (R_f) is the risk-free rate")
        st.write("- (σ) is the standard deviation of returns")

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
        st.write("- (σ) is the standard deviation of negative returns.")

        st.subheader("Calmar Ratio")
        st.write("A risk-adjusted return metric that compares the annualized return to the maximum drawdown.")
        st.latex(r"\text{Calmar Ratio} = \frac{\text{Annualized Return}}{\text{Max Drawdown}}")

        st.subheader("Profit Factor")
        st.write("The ratio of total profits to total losses.")
        st.latex(r"\text{Profit Factor} = \frac{\text{Total Profit}}{\text{Total Loss}}")

        st.subheader("Number of Trades")
        st.write("The total count of trades executed.")
        st.latex(r"\text{Number of Trades} = \text{Winning Trades} + \text{Losing Trades}")

    strategy_evaluation = get_strategy_evaluation(strategy_id)
    if strategy_evaluation is None or len(strategy_evaluation['metrics']) == 0:
        st.warning("No evaluation metrics to show. No orders have been executed.", icon=":material/smart_toy:")
    else:
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
        html_txt += """<div class="evaluation-metrics-container">"""
        for key, value in strategy_evaluation["metrics"].items():
            key = key.replace("_", " ")
            if key == "win rate":
                value = f"{round(value, 2)}%"
            html_txt += f"""<div class="evaluation-metric"><span class="evaluation-metric-name">{key}:</span> <span class="evaluation-metric-value">{value}</span></div>"""
        html_txt += """</div>"""
        st.html(html_txt)

        if st.button("Refresh Evaluation Metrics", icon=":material/update:", type="tertiary"):
            st.rerun()


def show_active_strategy_count(active_strategies: int, total_strategies: int):
    st.html(f"""
    <style>
        .strategy_count_container {{
            font-size: 18px;
            text-align: center;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .green-circle {{
            width: 12px;
            height: 12px;
            background: radial-gradient(circle, #3ee577 20%, #22c55e 80%);
            border-radius: 50%;
            box-shadow: 0px 0px 8px rgba(34, 197, 94, 0.7);
            display: inline-block;
            position: relative;
        }}
        .green-circle::before {{
            content: "";
            position: absolute;
            width: 26px;
            height: 26px;
            border-radius: 50%;
            background: rgba(34, 197, 94, 0.3);
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            animation: pulse 1.5s infinite;
        }}
        @keyframes pulse {{
            0% {{
                transform: translate(-50%, -50%) scale(1);
                opacity: 0.6;
            }}
            100% {{
                transform: translate(-50%, -50%) scale(1.4);
                opacity: 0;
            }}
        }}
        .sc_number {{
            font-weight: bold;
            color: #333;
            display: flex;
            align-items: center;
            gap: 5px;
        }}
    </style>

    <div class="strategy_count_container">
        There are 
        <span class="sc_number">
            <span class="green-circle"></span> {active_strategies}
        </span>
        active strategies and a total of <span class="sc_number">{total_strategies}</span>
    </div>
    """)


def color_rows(val):
    """
    Usage: logs_df.style.applymap(color_rows, subset=['order'])
    """
    if val == 'BUY':
        return 'background-color: lightgreen'
    elif val == 'SELL':
        return 'background-color: lightcoral'
    return ""


def strategy_plot_info() -> None:
    st.html("""
    <style>
      .triangle_buy {
        -webkit-text-stroke: 2px green;
        color: green;
        font-size: 14px;
        display: inline-block; /* Ensures it stays in the same line */
      }
    
      .triangle_sell {
        -webkit-text-stroke: 2px red;
        color: red;
        font-size: 14px;
        display: inline-block; /* Ensures it stays in the same line */
      }
      
      .triangle_buy_invalid {
        -webkit-text-stroke: 2px green;
        color: transparent;
        font-size: 14px;
        display: inline-block; /* Keeps it inline */
      }
      
      .triangle_sell_invalid {
        -webkit-text-stroke: 2px red;
        color: transparent;
        font-size: 14px;
        display: inline-block; /* Ensures it stays in the same line */
      }
      
    .triangle_buy_slippage {
        -webkit-text-stroke: 1px orange;
        color: transparent;
        font-size: 14px;
        display: inline-block; /* Keeps it inline */
      }

    .triangle_sell_slippage {
        -webkit-text-stroke: 1px purple;
        color: transparent;
        font-size: 14px;
        display: inline-block; /* Keeps it inline */
      }

    </style>
    
    <p style="font-size:15px; font-weight: 500; margin-bottom:0.2rem;">&#x2022; The lineplot shows the price over time from the initiation time of the strategy along with markers indicating 
        <span class="triangle_buy">&#9650;</span> <strong>BUY</strong> and 
        <span class="triangle_sell">&#9660;</span> <strong>SELL</strong> orders that were placed by the strategy. </p>
    <p style="font-size:15px; font-weight: 500; margin-bottom:0.2rem;">&#x2022;
        In case the signal is sent by the algorithm but the order fails, it will be denoted with 
        <span class="triangle_buy_invalid">&#9650;</span> <strong>Invalid BUY</strong> and 
        <span class="triangle_sell_invalid">&#9660;</span> <strong>Invalid SELL</strong>. The order might fail because the algorithm tried to perform 2 consecutive BUY or SELL orders, 
        because the balance was not enough or something went wrong with the Exchange API order command.
    </p>
    <p style="font-size:15px; font-weight: 500;">&#x2022;
        The plot can also indicate the <strong>slippage</strong>. The slippage marker shows how far off was the desired 
        price that the strategy used to make the order decision from the actual executed price. The desired price for the BUY order is denoted with 
        <span class="triangle_buy_slippage">&#9650;</span> and for SELL order slippage <span class="triangle_sell_slippage">&#9660;</span>.
    </p>
    """)


def strategy_info_card(strategy_id: str, quote_asset:str, base_asset: str, balance: float, time_interval: str, trades_limit: int, strategy_name: str, created_at: str, status: str) -> None:
    st.html(
        f"""
        <style>
            .strategy-card {{
                background-color: #f9f9f9;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                margin: 10px auto;
                max-width: 80%;
                text-align: center;
                font-family: 'Arial', sans-serif;
            }}
            .strategy-title {{
                font-size: 24px;
                font-weight: bold;
                color: #333;
                margin-bottom: 10px;
            }}
            .metrics-container {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 15px;
                margin-bottom: 15px;
            }}
            .metric-box {{
                background: white;
                border-radius: 8px;
                padding: 10px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                font-size: 16px;
                font-weight: bold;
                color: #444;
            }}
            .strategy-info {{
                font-size: 14px;
                color: #666;
                margin-top: 5px;
            }}
            .status-container {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                font-weight: bold;
            }}
            .status-indicator {{
                width: 12px;
                height: 12px;
                border-radius: 50%;
                background-color: {"#008000" if status == "active" else "#FF0000"};
                animation: {"pulse_card 1.5s infinite" if status == "active" else "fade 2s infinite"};
            }}
            @keyframes pulse_card {{
                0% {{ transform: scale(1); opacity: 0.8; }}
                50% {{ transform: scale(1.2); opacity: 1; }}
                100% {{ transform: scale(1); opacity: 0.8; }}
            }}
            @keyframes fade {{
                0% {{ opacity: 0.3; }}
                50% {{ opacity: 1; }}
                100% {{ opacity: 0.3; }}
            }}
        </style>

        <div class="strategy-card">
            <div class="strategy-title">Strategy {strategy_id} Overview</div>
            <div class="metrics-container">
                <div class="metric-box">Quote Asset: {quote_asset}</div>
                <div class="metric-box">Base Asset: {base_asset}</div>
                <div class="metric-box">Market: {base_asset}/{quote_asset}</div>
                <div class="metric-box">Time Interval: {time_interval}</div>
                <div class="metric-box">Initial Balance: {balance} {quote_asset}</div>
                <div class="metric-box">Trades Limit: {trades_limit}</div>
            </div>
            <div class="strategy-info">Strategy: <b>{strategy_name}</b></div>
            <div class="strategy-info">Deployed at: <b>{created_at}</b></div>
            <div class="strategy-info status-container">
                <div class="status-indicator"></div>
                Status: {status}
            </div>
        </div>
        """
    )
