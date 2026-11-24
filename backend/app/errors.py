class DBError(Exception):
    """Database/API error with a message that is safe to show to the user."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class AgentError(Exception):
    """AI error with a friendly message and the HTTP status to return."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status
