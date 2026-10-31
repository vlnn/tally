from datetime import datetime, timedelta

import pytest

from tally import store

NOW = datetime(2026, 10, 20, 15, 0)
NO_OFFSET = timedelta()
TODAY = NOW.date()

DAY = (
    (9, 5, "standup #team"),
    (9, 40, "mail"),
    (10, 10, ""),
    (11, 5, "parser #lexer"),
    (12, 50, ""),
    (13, 10, "call with ola"),
    (13, 40, "review pr 212"),
    (14, 5, "parser #lexer"),
)


@pytest.fixture
def db():
    return store.connect(":memory:")


@pytest.fixture
def logged(db):
    def log(hour, minute, line, day=TODAY, logged_at=None):
        at = datetime(day.year, day.month, day.day, hour, minute)
        return store.record(db, at, line, logged_at or at)

    return log


@pytest.fixture
def sample(logged):
    return [logged(*entry) for entry in DAY]


@pytest.fixture(autouse=True)
def no_mac(mocker):
    """The suite never reaches the machine it runs on: no `defaults`, `ioreg`, `pmset`,
    `launchctl`, `open` or `afplay`. A test that wants one of them patches it itself."""
    absent = mocker.MagicMock(returncode=1, stdout="")
    mocker.patch("subprocess.run", return_value=absent)
    mocker.patch("subprocess.Popen")
