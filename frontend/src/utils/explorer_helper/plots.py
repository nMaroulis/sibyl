from plotly import express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pandas import DataFrame
from streamlit import plotly_chart


def plot_block_height_weight_tx_count(df: DataFrame):
    df['Block Size'] = df['Block Size'] # convert to KBs

    fig = make_subplots(
        specs=[[{"secondary_y": True}]],  # This specifies the use of a secondary y-axis
        shared_xaxes=True  # This ensures that both plots share the same x-axis
    )

    # Add Block Size plot (on primary y-axis)
    fig.add_trace(
        go.Scatter(x=df['Block Height'], y=df['Block Size'], mode='lines', name='Block Size',
                   line=dict(color='blue')),
        secondary_y=False  # Place this trace on the primary y-axis
    )

    # Add Transaction Count plot (on secondary y-axis)
    fig.add_trace(
        go.Scatter(x=df['Block Height'], y=df['Transaction Count'], mode='lines', name='Transaction Count',
                   line=dict(color='green')),
        secondary_y=True  # Place this trace on the secondary y-axis
    )

    # Update layout to add titles and axis labels
    fig.update_layout(
        title="Block Size and Transaction Count vs Block Height",
        xaxis_title="Block Height",
        template="plotly_white",
        legend_title="Legend"
    )

    # Update the y-axes
    fig.update_yaxes(title_text="Block Size (KBs)", secondary_y=False)  # Primary y-axis
    fig.update_yaxes(title_text="Transaction Count", secondary_y=True)  # Secondary y-axis
    plotly_chart(fig, use_container_width=True)
    return
