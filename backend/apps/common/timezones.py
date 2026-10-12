from zoneinfo import available_timezones

DEFAULT_EVENT_TIMEZONE = "America/Argentina/Buenos_Aires"


def is_timezone(name: str) -> bool:
    return name in available_timezones()
