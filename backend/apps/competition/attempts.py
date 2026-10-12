"""The race session of a round and its attempts."""

from .models import Attempt, Round, Session


def race_session(round_: Round) -> Session:
    session, _ = Session.objects.get_or_create(round=round_, kind=Session.Kind.RACE)
    return session


def current_attempt(session: Session) -> Attempt:
    """The newest attempt. A session without attempts gets attempt 1."""
    attempt = session.attempts.order_by("-number").first()
    if attempt is None:
        attempt = Attempt.objects.create(session=session, number=1)
    return attempt


def accept_current_attempt(round_: Round) -> Attempt:
    """Mark the newest race attempt as the one that gives the classification."""
    attempt = current_attempt(race_session(round_))
    if attempt.status != Attempt.Status.ACCEPTED:
        attempt.status = Attempt.Status.ACCEPTED
        attempt.save(update_fields=["status"])
    return attempt
