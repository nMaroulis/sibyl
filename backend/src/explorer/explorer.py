import requests
from pandas import to_datetime
from datetime import datetime


class Explorer:

    def __init__(self, blockchain: str):
        self.blockchain: str = blockchain

    def get_blocks(self, limit: int) -> list | None:
        if self.blockchain == "bitcoin":
            blocks = []

            # Fetch the height of the latest block
            tip_url = "https://blockstream.info/api/blocks/tip/height"
            response = requests.get(tip_url)
            if response.status_code != 200:
                return None

            latest_height = response.json()  # Get the latest block height
            current_height = latest_height

            # Fetch blocks starting from the latest block height, iteratively going backward
            while len(blocks) < limit and current_height >= 0:
                url = f"https://blockstream.info/api/blocks/{current_height}"
                response = requests.get(url)
                if response.status_code != 200:
                    break

                data = response.json()

                # Fetch each block's details
                for block in data:
                    block_height = block['height']
                    block_details_response = requests.get(f"https://blockstream.info/api/block/{block['id']}")
                    if block_details_response.status_code != 200:
                        continue

                    block_details = block_details_response.json()
                    block_time = block_details['timestamp']  # Unix timestamp
                    transaction_count = block_details['tx_count']
                    size = block_details['size']
                    weight = block_details['weight']
                    difficulty = block_details['difficulty']
                    # mediantime = block_details['mediantime']

                    blocks.append({
                        'Block Height': block_height,
                        'Date': to_datetime(block_time, unit='s'),
                        'Transaction Count': transaction_count,
                        'Block Size': size/1024,  # convert to KBs
                        'Block Weight': weight,
                        'Difficulty': difficulty,
                        # 'Median Time-Past': mediantime,
                    })

                    if len(blocks) >= limit:
                        break

                # Move to the previous set of blocks by decreasing the block height
                current_height -= 10  # Each request gets 10 blocks

            return blocks
        elif self.blockchain == "litecoin":
            response = requests.get(f"https://api.blockchair.com/litecoin/blocks?limit={limit}")
            if response.status_code != 200:
                print(response, response.json())
                return None

            blocks = response.json().get('data', [])
            data = []

            for block in blocks:
                block_time = datetime.fromisoformat(block['time'].replace('Z', ''))
                transaction_count = block['transaction_count']
                data.append({
                    'Date': block_time,
                    'Block Time (min)': block['median_block_time'] / 60 if 'median_block_time' in block else None,
                    'Transaction Count': transaction_count,
                    'Transaction Fee (LTC)': block['fee_total'] / 1e8  # Convert to LTC
                })
            return data
        else:
            return None
