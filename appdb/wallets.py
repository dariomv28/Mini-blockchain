"""Wallet repository facade; secrets are never serialized by routes."""

class WalletRepository:
    def __init__(self, database):
        self.database = database

    def get_by_user_id(self, user_id):
        return self.database.wallet(user_id)
