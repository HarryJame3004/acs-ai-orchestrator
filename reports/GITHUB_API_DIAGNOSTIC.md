# GitHub API connectivity diagnosis

Verification label: CLOUD_REAL. Current outcome: PASS.

| Check | Observed result |
|---|---|
| Unauthenticated Python GET https://api.github.com/ | HTTP 200, JSON response and GitHub request ID |
| Curl HTTPS proxy CONNECT to api.github.com | HTTP 200 |
| Curl API response after CONNECT | HTTP/2 200, GitHub request ID |
| Curl TLS certificate verification | Result 0 (successful), verification enabled |
| Curl github.com and PyPI controls | CONNECT 200, HTTP 200 |
| Existing-auth REST repository metadata | Success; repository pull/push permission metadata present |
| Existing-auth GraphQL PR query | Success; PR #1 OPEN, mergedAt null |

The earlier `Tunnel connection failed: 403 Forbidden` occurred at proxy CONNECT,
before GitHub TLS/application authentication. It was a network/proxy refusal,
not a GitHub credential or repository-permission response. It does not reproduce
after the user's network-settings check. Current transport and existing API
authentication both work. No credential values were read or printed, no token
was replaced, and no certificate/proxy verification was disabled.

The normal supported route uses HTTPS_PROXY at proxy:8080. Testing did not
bypass the environment proxy. A Python github.com HTML probe using an API Accept
header returned a GitHub-origin 406 with a request ID; the ordinary curl control
returned 200. That response was unrelated to the historical CONNECT refusal.

The chat-bound editable draft still reports restricted access with an explicit
api.github.com rule and package-manager presets. This is draft metadata, not a
live policy inspection; it differs from the user's reported All setting. These
observations do not establish which UI/publication change restored access. The
successful runtime requests establish that this active task can now use the API.
No configuration was overwritten during this diagnosis.

No environment republication or task restart is required to restore GitHub API
connectivity in the current task. Publishing pending setup/snapshot changes is
a separate persistence action, not a prerequisite for the now-successful calls.
If a future task has different runtime policy, retest its actual connection
rather than assuming this task's result applies to it.

No PR merge, repository setting change, credential operation or deployment was
performed. Stage 0 remains open; safe subsequent work can use dependent branches
under the user's existing continuation authorization.
