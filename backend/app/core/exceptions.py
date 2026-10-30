class PriceMonitorError(Exception):
    """Base class for domain errors."""


class CaptchaRequired(PriceMonitorError):
    """The platform presented a captcha; a human must complete it."""


class LoginRequired(PriceMonitorError):
    """The platform session is missing or expired."""


class ShopNotAllowed(PriceMonitorError):
    """The listing's shop is not an official flagship/self-operated store."""


class ParseError(PriceMonitorError):
    """The page structure could not be parsed."""
