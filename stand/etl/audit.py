"""Сверка автоправил со словарём: сколько пар написаний правила склеили верно,
сколько ложно и сколько пропустили."""
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Agreement:
    tp: int   # склеено и правилами, и словарём
    fp: int   # склеено правилами, словарь разделил
    fn: int   # склеено словарём, правила не склеили

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0


def _pairs(groups: Counter) -> int:
    return sum(n * (n - 1) // 2 for n in groups.values())


def pair_agreement(rules: dict[str, str], truth: dict[str, str]) -> Agreement:
    keys = [k for k in truth if k in rules]
    both = _pairs(Counter((rules[k], truth[k]) for k in keys))
    return Agreement(both,
                     _pairs(Counter(rules[k] for k in keys)) - both,
                     _pairs(Counter(truth[k] for k in keys)) - both)
