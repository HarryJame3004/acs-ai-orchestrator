# Recovery test fixture publication correction

Retained run `combined-final-root` at 1bb7b7f reported 284 passed, one failed,
seven local skips. The failed recovery test read an empty string from its PID
readiness marker and raised JSONDecodeError before killing the controller.
The original fixture used Path.write_text: the pathname becomes visible when
opened, before the JSON is fully written. Polling exists() was therefore not a
valid completion notification. This is a fixture communication race, not proof
that controller-death cleanup failed.

Only the fixture publisher changes: it writes a sibling pending file completely,
closes it and atomically replaces the readiness marker. Every original timeout,
PID check, controller-kill, descendant cleanup and unrelated-sibling assertion is
preserved. There is no JSON parse retry, longer timeout, skip, or assertion removal.
The correction is committed separately, as required for genuinely incorrect
existing tests. Original failure evidence remains in the retained directory and
adjacent JSON/text reports; a later passing run does not erase it.
