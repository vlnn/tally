"""Which tasks a list is about: everything, or only those carrying one tag."""

from __future__ import annotations

from typing import NamedTuple

from hoard.alfred import fold

from tally import store, tags

DEFAULT_WORK_TAG = "w"


class Scope(NamedTuple):
    tag: str = ""
    aliases: dict = {}  # noqa: RUF012

    @property
    def label(self) -> str:
        return f"#{self.aliases.get(self.tag, self.tag)}" if self.tag else ""

    def holds(self, line: str) -> bool:
        return not self.tag or self.label in tags.of(tags.canonical(line, self.aliases))

    def apply(self, line: str) -> str:
        return line if self.holds(line) else f"{line} #{self.tag}"

    def identity(self, line: str) -> str:
        return fold(store.tidy(tags.canonical(line, self.aliases)))

    def same(self, one: str, other: str) -> bool:
        return self.identity(one) == self.identity(other)


def work(setting: str, aliases: dict) -> Scope:
    return Scope(tags.key(setting) or DEFAULT_WORK_TAG, aliases)
