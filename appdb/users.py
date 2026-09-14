"""User repository facade."""

class UserRepository:
    def __init__(self, database):
        self.database = database

    def get_by_id(self, user_id):
        return self.database.user(user_id)

    def find(self, identifier):
        return self.database.find_user(identifier)
