from typing import Dict, List
from collections import defaultdict


def invert_dict(original_dict: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Inverts a dictionary where the original values (lists) become keys,
    and the original keys become elements in new lists.

    Args:
        original_dict (Dict[str, List[str]]):
            A dictionary where keys map to a list of values.

    Returns:
        Dict[str, List[str]]:
            A dictionary where each value from the original dictionary
            is now a key, and its associated values are the original keys.

    Example:
        >> data = {
        ...     "USDT": ["BTC", "ETH", "ADA"],
        ...     "BTC": ["ETH", "SOL"],
        ...     "BUSD": ["BNB", "ADA"]
        ... }
        >> invert_dict(data)
        {
            "BTC": ["USDT"],
            "ETH": ["USDT", "BTC"],
            "ADA": ["USDT", "BUSD"],
            "SOL": ["BTC"],
            "BNB": ["BUSD"]
        }
    """
    inverted: Dict[str, List[str]] = defaultdict(list)

    for key, values in original_dict.items():
        for value in values:
            inverted[value].append(key)

    return dict(inverted)
