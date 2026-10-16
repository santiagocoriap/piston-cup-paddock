from contextlib import contextmanager

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from ninja import Schema
from ninja.errors import HttpError


class Error(Schema):
    detail: str


@contextmanager
def conflict_on_duplicate(detail: str):
    """Turn a unique constraint error into HTTP 409."""
    try:
        with transaction.atomic():
            yield
    except IntegrityError as error:
        raise HttpError(409, detail) from error


@contextmanager
def conflict_on_protected(detail: str = "in_use"):
    """Turn a delete that a protected row blocks into HTTP 409. Nothing is deleted."""
    try:
        with transaction.atomic():
            yield
    except ProtectedError as error:
        raise HttpError(409, detail) from error


def require(allowed: bool, status: int = 403, detail: str = "forbidden") -> None:
    if not allowed:
        raise HttpError(status, detail)
