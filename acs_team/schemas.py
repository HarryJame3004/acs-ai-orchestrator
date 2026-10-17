"""Versioned strict worker data; parsing never executes commands or instructions."""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .ownership import scope
from .security import verification_argv

Text = Annotated[str, Field(min_length=1, max_length=4096)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1] = 1


class Task(Data):
    task_id: Identifier
    title: Text
    description: Text
    worker: Identifier = "auto"
    role: Literal["planner", "implementer", "tester", "reviewer", "integrator"] = (
        "implementer"
    )
    owns: list[str] = Field(min_length=1, max_length=128)
    reads: list[str] = Field(default_factory=list, max_length=128)
    depends_on: list[Identifier] = Field(default_factory=list, max_length=64)
    acceptance_criteria: list[Text] = Field(min_length=1, max_length=32)
    verification_commands: list[list[str]] = Field(min_length=1, max_length=8)
    risk_level: Literal["low", "medium", "high"] = "medium"
    contract_hashes: list[Annotated[str, Field(pattern="^[a-f0-9]{64}$")]] = Field(
        default_factory=list, max_length=32
    )

    @field_validator("owns", "reads")
    @classmethod
    def valid_scopes(cls, values):
        for value in values:
            scope(value)
        if len(set(v.casefold() for v in values)) != len(values):
            raise ValueError("Duplicate ownership")
        return values

    @field_validator("verification_commands")
    @classmethod
    def valid_commands(cls, commands):
        for command in commands:
            if len(command) > 64 or any(len(a) > 512 for a in command):
                raise ValueError("Verification command too large")
            verification_argv(command)
        return commands


class Plan(Data):
    mission_id: Identifier
    requirements: list[Text] = Field(min_length=1, max_length=64)
    tasks: list[Task] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def valid_graph(self):
        tasks = {t.task_id: t for t in self.tasks}
        if len(tasks) != len(self.tasks) or sum(len(t.owns) for t in self.tasks) > 256:
            raise ValueError("Duplicate tasks or scope budget exceeded")
        visiting, visited = set(), set()

        def visit(name):
            if name not in tasks:
                raise ValueError("Unknown dependency")
            if name in visiting:
                raise ValueError("Dependency cycle")
            if name in visited:
                return
            visiting.add(name)
            for dependency in tasks[name].depends_on:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)

        for name in tasks:
            visit(name)
        return self


class Review(Data):
    task_id: Identifier
    implementer: Identifier
    reviewer: Identifier
    commit_sha: Annotated[str, Field(pattern="^[a-f0-9]{40,64}$")]
    verdict: Literal["PASS", "FIX_REQUIRED", "REPLAN"]
    requirement_coverage: list[Text] = Field(min_length=1, max_length=64)
    findings: list[Text] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def independent(self):
        if self.implementer == self.reviewer:
            raise ValueError("Reviewer must be a different worker instance")
        if self.verdict == "PASS" and self.findings:
            raise ValueError("Passing review cannot contain unresolved findings")
        return self


class Message(Data):
    mission_id: Identifier
    task_id: Identifier
    sender: Identifier
    recipient: Identifier
    kind: Literal["handoff", "question", "blocker", "decision", "review", "status"]
    payload: dict = Field(max_length=32)
    artifacts: list[Annotated[str, Field(max_length=512)]] = Field(
        default_factory=list, max_length=16
    )


class TaskResult(Data):
    task_id: Identifier
    worker: Identifier
    success: bool
    summary: Text
    artifacts: list[Text] = Field(default_factory=list, max_length=32)


T = TypeVar("T", bound=Data)


def parse_data(model: type[T], raw: bytes | str, max_bytes: int = 65536) -> T:
    encoded = raw.encode() if isinstance(raw, str) else raw
    if len(encoded) > max_bytes:
        raise ValueError("Structured payload exceeds size budget")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    try:
        value = json.loads(
            encoded,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("Invalid JSON number")
            ),
        )
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid structured JSON") from exc
    return model.model_validate(value)


def plan_lint(plan: Plan) -> list[str]:
    return [
        f"{task.task_id}: no test path in ownership"
        for task in plan.tasks
        if not any(re.search(r"(^|/)(test|tests)", p) for p in task.owns)
    ]
