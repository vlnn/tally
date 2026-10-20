from datetime import datetime

import pytest

from conftest import NOW
from tally import timewords


@pytest.mark.parametrize(
    "text, line, at",
    [
        ("parser", "parser", None),
        ("parser 14:05", "parser", datetime(2026, 10, 20, 14, 5)),
        ("parser 9:30", "parser", datetime(2026, 10, 20, 9, 30)),
        ("parser -20m", "parser", datetime(2026, 10, 20, 14, 40)),
        ("parser -1h", "parser", datetime(2026, 10, 20, 14, 0)),
        ("parser -1h20m", "parser", datetime(2026, 10, 20, 13, 40)),
        ("call at 14:00 with ola", "call at 14:00 with ola", None),
        ("pr 212", "pr 212", None),
        ("fix -5", "fix -5", None),
        ("parser 25:00", "parser 25:00", None),
    ],
)
def test_only_the_last_word_may_be_a_time(text, line, at):
    typed = timewords.parse(text, NOW)
    assert (typed.line, typed.at, typed.problem) == (line, at, ""), (
        "a trailing time word is the start; anything else stays in the line"
    )


@pytest.mark.parametrize(
    "text, problem",
    [
        ("parser 16:30", "16:30 has not happened yet"),
        ("14:30", "Type what you were doing before the time"),
        ("-20m", "Type what you were doing before the time"),
    ],
)
def test_impossible_times_explain_themselves(text, problem):
    assert timewords.parse(text, NOW).problem == problem, "the row says why it cannot act"


def test_now_itself_is_allowed():
    assert timewords.parse("parser 15:00", NOW).at == NOW, "a start at now is just a start"
