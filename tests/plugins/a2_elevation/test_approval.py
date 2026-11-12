"""FirstAnswerApprover: the first decisive channel wins, the others are stopped and told the outcome."""

import threading

from tests.plugins.a2_elevation.conftest import load

approval = load("approval")
Outcome = approval.Outcome

WAIT_LIMIT = 10.0


class ScriptedApprover(approval.Approver):
    """Answers ``outcome`` (after ``release`` when given) or, without one, waits until stopped."""

    def __init__(self, channel, outcome=None, *, release=None, password_capable=True, error=None):
        self.channel = channel
        self._outcome = outcome
        self._release = release
        self._password_capable = password_capable
        self._error = error
        self.asked = threading.Event()
        self.stopped = False
        self.concluded = []

    def supports(self, request):
        return self._password_capable or not request.needs_password

    def ask(self, request, stop):
        self.asked.set()
        if self._error is not None:
            raise self._error
        if self._outcome is None:
            assert stop.wait(WAIT_LIMIT)
            self.stopped = True
            return approval.ApprovalResult(Outcome.SUPERSEDED, self.channel)
        if self._release is not None:
            assert self._release.wait(WAIT_LIMIT)
        return approval.ApprovalResult(self._outcome, self.channel, actor=f"{self.channel}-actor")

    def conclude(self, request, final):
        self.concluded.append(final)


def _request(needs_password=False):
    return approval.ApprovalRequest(reason="Deploy", scope="protected", scope_label="Bereich",
                                    needs_password=needs_password)


def test_first_decisive_answer_wins_and_stops_the_other_channel():
    mac = ScriptedApprover("mac")
    telegram = ScriptedApprover("telegram", Outcome.APPROVED)

    final = approval.FirstAnswerApprover([mac, telegram]).ask(_request())

    assert (final.outcome, final.channel) == (Outcome.APPROVED, "telegram")
    assert mac.stopped
    assert mac.concluded == [final] and telegram.concluded == [final]


def test_denial_also_wins_the_race():
    final = approval.FirstAnswerApprover([
        ScriptedApprover("mac", Outcome.DENIED), ScriptedApprover("telegram"),
    ]).ask(_request())

    assert (final.outcome, final.channel) == (Outcome.DENIED, "mac")


def test_unavailable_channel_does_not_end_the_race():
    release = threading.Event()
    mac = ScriptedApprover("mac", Outcome.APPROVED, release=release)
    telegram = ScriptedApprover("telegram", Outcome.UNAVAILABLE)
    result = {}
    worker = threading.Thread(target=lambda: result.update(final=approval.FirstAnswerApprover([mac, telegram]).ask(_request())))
    worker.start()
    assert mac.asked.wait(WAIT_LIMIT)
    release.set()
    worker.join(WAIT_LIMIT)

    assert (result["final"].outcome, result["final"].channel) == (Outcome.APPROVED, "mac")


def test_timeout_when_nobody_decides():
    final = approval.FirstAnswerApprover([
        ScriptedApprover("mac", Outcome.TIMED_OUT), ScriptedApprover("telegram", Outcome.UNAVAILABLE),
    ]).ask(_request())

    assert final.outcome is Outcome.TIMED_OUT


def test_unavailable_when_every_channel_fails():
    final = approval.FirstAnswerApprover([
        ScriptedApprover("mac", error=OSError("no swiftc")), ScriptedApprover("telegram", Outcome.UNAVAILABLE),
    ]).ask(_request())

    assert final.outcome is Outcome.UNAVAILABLE
    assert "no swiftc" in final.detail


def test_password_requests_skip_channels_that_cannot_carry_one():
    telegram = ScriptedApprover("telegram", Outcome.APPROVED, password_capable=False)
    mac = ScriptedApprover("mac", Outcome.DENIED)

    final = approval.FirstAnswerApprover([telegram, mac]).ask(_request(needs_password=True))

    assert (final.outcome, final.channel) == (Outcome.DENIED, "mac")
    assert not telegram.asked.is_set()
    assert telegram.concluded == []


def test_no_capable_channel_is_unavailable():
    final = approval.FirstAnswerApprover([
        ScriptedApprover("telegram", Outcome.APPROVED, password_capable=False),
    ]).ask(_request(needs_password=True))

    assert final.outcome is Outcome.UNAVAILABLE


def test_result_repr_never_shows_the_password():
    result = approval.ApprovalResult(Outcome.APPROVED, "mac", password="geheim")

    assert "geheim" not in repr(result)
