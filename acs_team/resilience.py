"""Bounded provider retries, explicit error classes and a clock-testable circuit."""

from dataclasses import dataclass
from enum import Enum
import random
import time
from typing import Callable


class FailureKind(str, Enum):
    TRANSIENT = "transient"
    QUOTA = "quota"
    AUTH = "auth"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


def classify(status: int | None = None, error: Exception | None = None) -> FailureKind:
    if status in {401, 403}:
        return FailureKind.AUTH
    if status == 429:
        return FailureKind.QUOTA
    if status is not None:
        return FailureKind.TRANSIENT if status >= 500 or status in {408, 425} else FailureKind.PERMANENT
    return FailureKind.TRANSIENT if isinstance(error, (TimeoutError, ConnectionError)) else FailureKind.UNKNOWN


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base: float = 0.25
    maximum: float = 5

    def delay(self, attempt: int, rng: Callable[[], float] = random.random) -> float:
        return min(self.maximum, self.base * 2 ** min(attempt, 20)) * (0.8 + 0.2 * rng())


class CircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown: float = 60, clock: Callable[[], float] = time.monotonic):
        if threshold < 1 or cooldown < 0:
            raise ValueError("Invalid circuit limits")
        self.threshold, self.cooldown, self.clock = threshold, cooldown, clock
        self.failures = 0
        self.until = 0.0

    def allow(self) -> bool:
        return self.clock() >= self.until

    def failure(self, kind: FailureKind) -> None:
        self.failures += 1
        if kind == FailureKind.AUTH or self.failures >= self.threshold:
            self.until = self.clock() + self.cooldown

    def success(self) -> None:
        self.failures = 0
        self.until = 0
