import numpy as np
from typing import List, Dict, Any


class Evaluator:
    """
    A class to evaluate the performance of a trading strategy based on its trade history.
    It computes various financial metrics such as profit, Sharpe ratio, maximum drawdown, win rate, and more.

    Example usage:
        $ tactician = Tactician(exchange, symbol)
        $ tactician.run_strategy(strategy)
        $ evaluator = Evaluator(tactician.get_trade_history())
        $ metrics = evaluator.evaluate()
        $ print(metrics)
    """

    def __init__(self, trade_history: List[Dict[str, Any]], risk_free_rate: float = 0.0) -> None:
        """
        Initializes the Evaluator with trade history data.

        Args:
            trade_history (List[Dict[str, Any]]): A list of executed trades with 'order', 'price', 'amount'.
            risk_free_rate (float): The risk-free rate used in the Sharpe ratio calculation.
        """
        self.trade_history = trade_history
        self.risk_free_rate = risk_free_rate

    def calculate_profit(self) -> float:
        """
        Calculates the total profit or loss based on executed trades.

        Returns:
            float: The total profit or loss from all completed trades.
        """
        total_profit = 0.0
        buy_price = None
        buy_amount = 0.0

        for trade in self.trade_history:
            if trade["order"] == "BUY":
                buy_price = trade["price"]
                buy_amount = trade["amount"]
            elif trade["order"] == "SELL" and buy_price is not None:
                sell_price = trade["price"]
                total_profit += (sell_price - buy_price) * buy_amount
                buy_price = None  # Reset buy price after the sale

        return total_profit

    @staticmethod
    def calculate_max_drawdown(prices: List[float]) -> float:
        """
        Calculates the maximum drawdown, i.e., the largest peak-to-trough loss.

        Args:
            prices (List[float]): The list of asset prices during the strategy's run.

        Returns:
            float: The maximum drawdown as a percentage.
        """
        peak = prices[0]
        drawdowns = [0]  # No drawdown on the first day

        for price in prices[1:]:
            peak = max(peak, price)
            drawdowns.append((peak - price) / peak)

        return max(drawdowns) * 100

    def calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """
        Calculates the Sharpe ratio for the strategy based on returns.

        Args:
            returns (List[float]): A list of strategy returns per time period.

        Returns:
            float: The Sharpe ratio.
        """
        mean_return = np.mean(returns)
        std_dev_return = np.std(returns)
        return (mean_return - self.risk_free_rate) / std_dev_return if std_dev_return != 0 else 0

    def calculate_win_rate(self) -> float:
        """
        Calculates the win rate of the strategy, i.e., the percentage of profitable trades.

        Returns:
            float: The win rate as a percentage.
        """
        profitable_trades = [trade for trade in self.trade_history if trade["order"] == "SELL" and (
                trade["price"] > self.trade_history[self.trade_history.index(trade) - 1]["price"])]
        return len(profitable_trades) / len(
            [trade for trade in self.trade_history if trade["order"] == "SELL"]) * 100 if len(
            self.trade_history) > 0 else 0

    def calculate_average_win_loss(self) -> Dict[str, float]:
        """
        Calculates the average profit and average loss for the winning and losing trades.

        Returns:
            Dict[str, float]: A dictionary containing the average win and average loss.
        """
        wins = [trade for trade in self.trade_history if trade["order"] == "SELL" and (
                trade["price"] > self.trade_history[self.trade_history.index(trade) - 1]["price"])]
        losses = [trade for trade in self.trade_history if trade["order"] == "SELL" and (
                trade["price"] < self.trade_history[self.trade_history.index(trade) - 1]["price"])]

        avg_win = np.mean(
            [trade["price"] - self.trade_history[self.trade_history.index(trade) - 1]["price"] for trade in
             wins]) if wins else 0
        avg_loss = np.mean(
            [trade["price"] - self.trade_history[self.trade_history.index(trade) - 1]["price"] for trade in
             losses]) if losses else 0

        return {"average_win": avg_win, "average_loss": avg_loss}

    def calculate_sortino_ratio(self, returns: List[float]) -> float:
        """
        Calculates the Sortino ratio, which penalizes negative returns more heavily than positive ones.

        Args:
            returns (List[float]): A list of strategy returns per time period.

        Returns:
            float: The Sortino ratio.
        """
        downside_returns = [r for r in returns if r < 0]
        mean_return = np.mean(returns)
        downside_deviation = np.std(downside_returns) if downside_returns else 0
        return (mean_return - self.risk_free_rate) / downside_deviation if downside_deviation != 0 else 0

    @staticmethod
    def calculate_calmar_ratio(annual_return: float, max_drawdown: float) -> float:
        """
        Calculates the Calmar ratio, which measures the relationship between the average annual return
        and the maximum drawdown.

        Args:
            annual_return (float): The annualized return of the strategy.
            max_drawdown (float): The maximum drawdown of the strategy.

        Returns:
            float: The Calmar ratio.
        """
        return annual_return / max_drawdown if max_drawdown != 0 else 0


    def calculate_profit_factor(self) -> float:
        """
        Calculates the profit factor, which is the ratio of gross profit to gross loss.

        Returns:
            float: The profit factor. Returns None if there are no losses and no profits.
        """
        gross_profit = sum(
            trade["price"] - self.trade_history[i - 1]["price"]
            for i, trade in enumerate(self.trade_history[1:], start=1)
            if trade["order"] == "SELL" and trade["price"] > self.trade_history[i - 1]["price"]
        )

        gross_loss = abs(
            sum(
                trade["price"] - self.trade_history[i - 1]["price"]
                for i, trade in enumerate(self.trade_history[1:], start=1)
                if trade["order"] == "SELL" and trade["price"] < self.trade_history[i - 1]["price"]
            )
        )

        if gross_loss == 0:
            return gross_profit if gross_profit > 0 else 0.0  # Return gross profit or 0.0 instead of NaN/Inf

        return round(gross_profit / gross_loss, 6)  # Avoid floating point precision issues


    @staticmethod
    def clean_json(data: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in data.items():
            if isinstance(value, np.float64) and (np.isnan(value) or np.isinf(value)):
                data[key] = "N/A"
        return data


    def evaluate(self) -> Dict[str, Any]:
        """
        Evaluates the strategy's performance by calculating key financial metrics:
        - Total profit/loss
        - Sharpe ratio
        - Maximum drawdown
        - Win rate
        - Average win and loss
        - Sortino ratio
        - Calmar ratio
        - Profit factor

        Returns:
            dict: A dictionary with evaluation metrics.
        """

        if self.trade_history:
            try:
                # profit = self.calculate_profit() # TODO

                # Extract closing prices for metrics
                closing_prices = [trade["price"] for trade in self.trade_history if trade["order"] == "SELL"]

                # Calculate returns from the closing prices
                returns = [100 * (closing_prices[i] - closing_prices[i - 1]) / closing_prices[i - 1]
                           for i in range(1, len(closing_prices))]

                max_drawdown = self.calculate_max_drawdown(closing_prices)
                win_rate = self.calculate_win_rate()
                avg_win_loss = self.calculate_average_win_loss()
                sortino_ratio = self.calculate_sortino_ratio(returns)
                calmar_ratio = self.calculate_calmar_ratio(np.mean(returns) * 252, max_drawdown)  # Annualized return assumption
                profit_factor = self.calculate_profit_factor()

                evaluation_results = {
                    "total_profit": 'N/A',  # profit,
                    "sharpe_ratio": self.calculate_sharpe_ratio(returns),
                    "max_drawdown": max_drawdown,
                    "win_rate": win_rate,
                    "average_win": avg_win_loss["average_win"],
                    "average_loss": avg_win_loss["average_loss"],
                    "sortino_ratio": sortino_ratio,
                    "calmar_ratio": calmar_ratio,
                    "profit_factor": profit_factor,
                    "number_of_trades": len(closing_prices),
                }
                evaluation_results = self.clean_json(evaluation_results)
                return evaluation_results
            except Exception as e:
                print("Strategy Evaluator :: evaluate :: ", e)
                return {}
        else:
            return {}