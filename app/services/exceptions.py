class InvalidCredentialsError(Exception):
    pass


class InactiveAccountError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


class NoSSOConnectionError(Exception):
    pass


class InvalidSSOStateError(Exception):
    pass


class MissingEmailClaimError(Exception):
    pass