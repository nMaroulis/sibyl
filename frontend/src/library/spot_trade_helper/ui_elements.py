from extra_streamlit_components import stepper_bar
from streamlit import write, container, expander, html, caption, link_button, tabs, error, info, divider, fragment, warning
from streamlit.components.v1 import html as components_html
from frontend.src.library.spot_trade_helper.client import fetch_orderbook


def get_spot_trade_instructions(exp=False):

    with expander('📖 Trading Instructions', expanded=exp):
        str_val = stepper_bar(steps=["Asset Options", "Trading Options", "Exchange Parameters", "Submission"], lock_sequence=False)
        if str_val == 0:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Asset Options</h5>""")
                tab0, tab1 = tabs(["Standard Order", "Quote Market Order"])
                with tab0:
                    write("1. Choose a ***Quote Asset***: This is the asset which you have to have in the account and will be use to **Buy** the **Base Asset**")
                    caption("Currently only USDT is available as an Asset to use for Trading.")
                    write("2. Choose a ***Base Asset***: This is the asset which you will buy, using the Quote Asset.")
                    write("3. Choose a ***Quantity***: This indicates how much of ***Base Asset*** (e.g. BTC) you will buy.")
                    write("**Example**: To buy 1 ETH with USDT you have on your account, you will choose: -Quote Asset: USDT, - Base Asset: ETH, quantity: 1.")
                with tab1:
                    write("This option is similar to the standard order, the only difference is you specify the amount of the Quote Asset you want to spend.")
                    write("**Example**: You want to buy 10 USDT worth of ETH. You will choose: -Quote Asset: USDT, - Base Asset: ETH, quote_quantity: 10. This way you define how much you want to spend and not how much you want to buy.")
                    info("**Note**: This option is only available in Market orders.", icon=":material/info:")
                    error("This option is not yet available.", icon=":material/warning:")
        if str_val == 1:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Trading Options</h5>""")
                write("""**Order Type**""")
                write("""1. **Market Order** – Executes immediately at the current market price. Suitable for quick trades but may incur higher "taker" fees.""")
                write("""2. **Limit Order** – Allows you to set a specific price at which you want to buy or sell. This order is placed on the order book and may incur lower "maker" fees.""")
                write("""3. **Stop-Loss Order** – Triggers a market sell order when the asset price falls to a specified "stop price." Used to minimize losses.""")
                write("""4. **Stop-Loss Limit Order** – Similar to a stop-loss, but instead of triggering a market order, it places a limit order once the stop price is reached.""")
                write("""5. **Take-Profit Order** – A market order that executes when the asset reaches a specified price, allowing you to secure profits automatically.""")
                write("""6. **Take-Profit Limit Order** – Similar to a take-profit order but executes as a limit order at a defined price.""")
                write("""7. **Trailing Stop Order** – A stop order that moves dynamically with price changes, protecting profits while minimizing downside risk.""")
                write("""8. **OCO (One-Cancels-the-Other)** – Combines a limit order and a stop-loss order, where if one order is executed, the other is automatically canceled.""")
                divider()
                write("""**Order Side**""")
                write("""- **Buy** – Purchase the selected Base asset.""")
                write("""- **Sell** – Sell the selected Base asset.""")
                divider()
                write("""**Pricing Fields**""")
                write("""- **Limit Price** – The price at which you are willing to buy/sell for limit orders.""")
                write("""- **Stop Price** – The price at which stop-loss and stop-limit orders trigger.""")
                write("""- **Take-Profit Price** – The price at which take-profit orders execute.""")
                divider()
                write("""**Additional Options**""")
                write("""**Percentage Mode** – If enabled, Stop-Loss and Take-Profit levels will be calculated as percentages rather than absolute values.""")
                write("""**Post-Only Order** – Ensures your limit order adds liquidity to the market by preventing it from executing immediately.""")
                write("""Time in Force (TIF) Options""")
                write("""- **GTC (Good-Til-Canceled)** – The order stays open until fully executed or manually canceled.""")
                write("""- **IOC (Immediate-Or-Cancel)** – The order is executed immediately for available liquidity, and any remaining portion is canceled.
                    FOK""")
                write("""- **FOK (Fill-Or-Kill)** – The order must be fully executed immediately or canceled entirely.""")
                write("""**Iceberg Quantity**: If entering a large order, an iceberg order allows only a portion of the total order to be visible on the order book at a time, helping to prevent large trades from impacting the market significantly.""")
        if str_val == 2:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Exchange Parameters</h5>""")
                write("**Token Swap Order**:")
                caption("Some Exchanges offer the **Token Swap** functionality, which directly swaps your Quote asset to the Base asset in market price with 0 fees.")
                write("1. The **Binance Convert** API enables trading with **0 fees**. If the backend server doesn't find a valid Convert API, the standard order will be used. If you are eligible to use the Convert functionality, the corresponding option will be shown below.")
                write("2. **Coinbase One** which provides zero trading fees among other benefits for a monthly fee of $29.99. This service allows users to buy, sell, and swap cryptocurrencies without incurring individual transaction fees, effectively enabling cost-effective crypto swaps.")
                write("3. Kraken has introduced a feature known as **Swaps** within the **Kraken Wallet**, therefore it is not enabled on the Kraken Exchange.")
                info("💡 For **Binance**,make sure to have **BNB** in your account in order to minimize the fees.")
        if str_val == 3:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Submission</h5>""")
                write("**Binance & Binance testnet**")
                write('First, a **test order** will be created to test if the order is possible based on the trade parameters. If it is not a message with the error from the Exchange API will be shown, otherwise the Trade will be placed.')
                write("**Coinbase & Coinbase sandbox**")
                write("Coinbase doesn't support test orders, so this step is skipped.")
                write("You can find ***Open Positions*** and ***Trading History*** in the **Trading Report module**.")
                link_button("Trading Report", "http://localhost:8501/trading_report ", type="primary", icon=":material/youtube_searched_for:")


import requests
from streamlit import fragment

def get_formatted_order_book(exchange: str, quote_asset: str, base_asset: str, limit: int = 10):
    return fetch_orderbook(exchange, quote_asset, base_asset, limit)


@fragment(run_every="4s")
def plot_orderbook(exchange: str, quote_asset: str, base_asset: str, limit: int):

    data = get_formatted_order_book(exchange, quote_asset, base_asset, limit)

    if data:
        max_bid_price = max(order['y'] for order in data[0])
        max_ask_price = max(order['y'] for order in data[1])

        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <script src="https://code.highcharts.com/highcharts.js"></script>
        </head>
        <body>
        <figure class="highcharts-figure">
            <div id="container"></div>
            <button id="animation-toggle" class="highcharts-demo-button">Stop animation</button>
        </figure>
    
        <script>
        function getRandomNumber(min, max) {{
            return Math.round(Math.random() * (max - min)) + min;
        }}
    
        function generateBidAndAskData(n) {{
            const data = {data}
            return data;
        }}
    
        const [bidsData, asksData] = generateBidAndAskData(10);
    
        function updateData(chart) {{
            const data = generateBidAndAskData(10);
            chart.series.forEach((s, i) => {{
                s.setData(data[i], false);
            }});
            chart.redraw();
        }}
    
        Highcharts.chart('container', {{
            chart: {{
                animation: {{
                    duration: 200
                }},
                type: 'bar',
                backgroundColor: '#F5F5F5',
                marginTop: 70,
                borderRadius: 10,  // Rounded corners
                shadow: true,  // Enables default shadow
                events: {{
                    load() {{
                        const chart = this,
                            toggleButton = document.getElementById('animation-toggle');
    
                        let intervalId = null;
                        const toggleInterval = () => {{
                            if (intervalId) {{
                                chart.update({{
                                    accessibility: {{
                                        enabled: true
                                    }}
                                }});
                                clearInterval(intervalId);
                                intervalId = null;
                                toggleButton.innerText = 'Start animation';
                            }} else {{
                                chart.update({{
                                    accessibility: {{
                                        enabled: false
                                    }}
                                }});
                                intervalId = setInterval(() => {{
                                    if (this.series) {{
                                        updateData(this);
                                    }}
                                }}, 2000);
                                toggleButton.innerText = 'Stop animation';
                            }}
                        }};
    
                        toggleButton.addEventListener('click', toggleInterval);
                        toggleInterval();
                    }}
                }}
            }},
    
            accessibility: {{
                point: {{
                    descriptionFormat: 'Price: {{price:.1f}}USD, ' +
                        '{{series.name}}: {{y}}'
                }}
            }},
    
            title: {{
                text: 'Order book live chart',
                style: {{
                    color: '#23232f'
                }}
            }},
    
            tooltip: {{
                headerFormat: 'Price: <b>${{point.point.price:,.1f}}</b></br>',
                pointFormat: '{{series.name}}: <b>{{point.y:,.0f}}</b>',
                shape: 'rect',
                positioner(labelWidth, _, point) {{
                    const {{ plotX, plotY, h }} = point,
                        negative = plotX < this.chart.yAxis[0].left;
    
                    return {{
                        x: negative ? plotX + h - labelWidth + 10 : plotX - h + 10,
                        y: plotY
                    }};
                }}
            }},
    
            xAxis: [{{
                reversed: true,
                visible: false,
                title: {{
                    text: 'Market depth / price'
                }},
                accessibility: {{
                    description: 'Bid orders'
                }}
            }}, {{
                opposite: true,
                visible: false,
                title: {{
                    text: 'Market depth / price'
                }},
                accessibility: {{
                    description: 'Ask orders'
                }}
            }}],
    
            yAxis: [{{
                offset: 0,
                visible: true,
                opposite: true,
                gridLineWidth: 0,
                tickAmount: 1,
                left: '50%',
                width: '50%',
                title: {{
                    text: 'Amount of ask orders',
                    style: {{
                        visibility: 'hidden'
                    }}
                }},
                min: 0,
                max: {max_ask_price},
                labels: {{
                    enabled: true,
                    format: '{{#if isLast}}Asks{{/if}}',
                    style: {{
                        color: '#23232f',
                        fontSize: 16,
                        fontWeight: 700
                    }},
                    y: 10
                }}
            }}, {{
                offset: 0,
                visible: true,
                opposite: true,
                gridLineWidth: 0,
                tickAmount: 2,
                left: '0%',
                width: '50%',
                reversed: true,
                title: {{
                    text: 'Amount of bid orders',
                    style: {{
                        visibility: 'hidden'
                    }}
                }},
                min: 0,
                max: {max_bid_price},
                labels: {{
                    enabled: true,
                    format: `
                        {{#if (eq pos 0)}}{base_asset} price in {quote_asset}{{/if}}
                        {{#if isLast}}Bids{{/if}}
                    `,
                    style: {{
                        color: '#23232f',
                        fontSize: 16,
                        fontWeight: 700
                    }},
                    y: 10
                }}
            }}],
    
            legend: {{
                enabled: false
            }},
    
            navigation: {{
                buttonOptions: {{
                    theme: {{
                        fill: 'none'
                    }}
                }}
            }},
    
            plotOptions: {{
                series: {{
                    animation: false,
                    pointPadding: 0,
                    groupPadding: 0,
                    dataLabels: {{
                        enabled: true,
                        color: '#23232f'
                    }},
                    borderWidth: 0,
                    crisp: false
                }}
            }},
    
            series: [{{
                dataLabels: [{{
                    align: 'right',
                    alignTo: 'plotEdges',
                    style: {{
                        fontSize: 14,
                        textOutline: 0
                    }},
                    format: '{{point.y:,.5f}}'
                }}, {{
                    align: 'left',
                    inside: true,
                    style: {{
                        fontSize: 13,
                        textOutline: 0
                    }},
                    format: '{{point.price:,.4f}}'
                }}],
                name: 'Asks',
                color: '#ce4548',
                data: asksData
            }}, {{
                dataLabels: [{{
                    align: 'left',
                    alignTo: 'plotEdges',
                    style: {{
                        fontSize: 14,
                        textOutline: 0
                    }},
                    format: '{{point.y:,.5f}}'
                }}, {{
                    align: 'right',
                    inside: true,
                    style: {{
                        fontSize: 13,
                        textOutline: 0
                    }},
                    format: '{{point.price:,.4f}}'
                }}],
                name: 'Bids',
                color:  '#107db7',
                data: bidsData,
                yAxis: 1
            }}]
        }});
        </script>
        </body>
        </html>
        """
        # Display in Streamlit
        components_html(html_code, height=400)
    else:
        warning(f"Failed to fetch orderbook for {quote_asset}/{base_asset}", icon=":material/two_pager:")

"""
Deprecated orderbook
    asks_df = pd.DataFrame(order_book["asks"], columns=["Ask Price", "Ask Quantity"]).astype(float)
    bids_df = pd.DataFrame(order_book["bids"], columns=["Bid Price", "Bid Quantity"]).astype(float)

    # Sort asks (lowest first) and bids (highest first)
    asks_df = asks_df.sort_values("Ask Price", ascending=True).reset_index(drop=True)
    bids_df = bids_df.sort_values("Bid Price", ascending=False).reset_index(drop=True)

    # Ensure same length for alignment
    max_rows = max(len(asks_df), len(bids_df))
    asks_df = asks_df.reindex(range(max_rows))
    bids_df = bids_df.reindex(range(max_rows))

    # Merge into one table with separate buy/sell columns
    order_book_df = pd.concat([bids_df, asks_df], axis=1)

    # Display order book with Streamlit table
    st.table(order_book_df.style.set_properties(**{"text-align": "center"}))
"""