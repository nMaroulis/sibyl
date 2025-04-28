class MemoryStore:
    def __init__(self):
        self.history = {}

    def get_memory(self, user_id: str) -> list:
        return self.history.get(user_id, [])

    def add_memory(self, user_id: str, interaction: dict):
        if user_id not in self.history:
            self.history[user_id] = []
        self.history[user_id].append(interaction)
