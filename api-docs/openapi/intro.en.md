# XHS Interface Layer API Guide

This guide explains the contract behind `openapi/openapi.base.yaml`. The OpenAPI
file is the source of truth for endpoint shapes. This guide is the source of
truth for workflow rules that are awkward to express in OpenAPI alone.

## Goals

- Provide an API-only XHS capability service.
- Keep the interface layer generic enough for MCP clients, app backends,
  scheduled jobs, and future adapters.
- Expose atomic tools instead of high-level business workflows.
- Keep DOM operations out of the first official interface surface.

## Session Model

A session is a long-lived isolated XHS identity container.

Each session owns exactly one browser profile directory. Different sessions
never share a profile directory. Reusing the browser profile means reusing the
same `session_id`.

The interface layer generates every `session_id` and creates the profile from
service defaults. Login state, current search results, the current note context,
and comment context are valid only within the current service process and reset
after process restart. The interface layer continues operations from
`session.json` plus the browser profile when needed. Callers store and reuse the
`session_id`; they do not choose stable names or paths.

## Binding Model

`session_id` is a resource identifier, not proof of ownership.

Normal applications can list sessions for discovery, occupancy checks, and
workflow coordination:

```text
GET /v1/sessions
```

The list endpoint does not return `user_data_dir`, tokens, cookies, raw
diagnostics, or other sensitive internal data.

Before a caller can mutate or crawl through a session, it must bind the session:

```text
create_session -> session_id
bind_session(session_id) -> token
operation(session_id, token, ...)
unbind_session(session_id, token)
```

Rules:

- A session can have at most one active token.
- The token has no TTL.
- The session remains occupied until the holder unbinds it or an admin force
  unbinds it.
- Public operations that mutate session state or crawl data require
  `session_id + token`.
- Pure status queries may accept an optional token for logging and traceability.

## Login

The HTTP surface uses one login endpoint:

```text
POST /v1/sessions/{session_id}/login
```

The request `action` selects the concrete behavior:

- `cookie`: import cookie into the session profile.
- `qrcode`: start or continue QR-code login and return the current challenge.
- `phone_start`: start phone login by sending a verification code.
- `phone_submit`: submit a phone verification code.

Status is queried separately:

```text
GET /v1/sessions/{session_id}/login/status
```

This is a pure query. Token is optional.

QR-code login can require multiple sequential challenges. For example, after the
initial login QR is scanned successfully, the platform may still require a
secondary security QR scan. Applications should always use the latest
`challenge.challenge_id` and `challenge.sequence` returned by `login/status`;
when either changes, refresh the displayed QR code.

Typical states:

- `waiting_qr_scan` + `required_action=scan_qr`: display the current QR code.
- `waiting_qr_confirm` + `required_action=confirm_qr`: scanned, waiting for
  phone-side confirmation.
- new `challenge.type=security_qr` with an increased `sequence`: display the
  second QR code.
- `ready` + `required_action=none`: login is complete.

## Strict Current-Position Mode

The interface layer enforces the current session context.

Search records the `note_id` values in the current search result. Opening a note
from a current search `note_id` or xsec parameters switches the current note
context. Comment operations can only run against the current note context.

Switching to a new note invalidates root comment context from the previous note.

This prevents mistakes such as opening note B and then accidentally fetching
comments for note A with stale `comment_id` values.

## Context Validation

The interface layer does not expose internal handles. Applications use platform
ids directly:

- `note_id`
- `comment_id`

The runtime records the current search results and current note comments in
memory. If a supplied id does not belong to the current context, the API returns
`stale_context` or `invalid_context`.

## Note Access

The note surface follows real platform access paths:

- `open-from-search`: open a note by `note_id` from the current search context.
- `open-by-xsec`: construct the pc_share URL from `note_id` and `xsec_token`.

Both operations update the current note context and return note detail data.

## Diagnostics

Every response includes shared lightweight `meta`. `request_id`, `operation`,
`retry_count`, and `warnings` are always returned. Optional fields such as
`session_id` and `diagnostics_ref` are returned only when they apply; the service
does not return `null` placeholders.

- `request_id`
- `session_id`
- `operation`
- `retry_count`
- `warnings`
- `diagnostics_ref`

Heavy diagnostics are queried separately:

```text
GET /v1/sessions/{session_id}/diagnostics
```

## Error Model

Error responses use one shared shape:

```json
{
  "ok": false,
  "error": {
    "code": "invalid_context",
    "message": "root_comment_id does not belong to current note context",
    "retryable": false,
    "action": "reopen_note",
    "details": {}
  },
  "meta": {}
}
```

`code` is the stable business error code and should be the primary field for
application branching. `message` is for humans and is not a stable programmatic
contract. `retryable` means the exact same request can be retried without
changing parameters or session context. `action` is the suggested next
application-layer step, such as `fix_request`, `login`, `reopen_note`,
`wait_and_retry`, or `contact_admin`.

Each endpoint response section lists possible HTTP statuses, error codes,
possible causes, and suggested actions.

## Retry Rules

The interface layer may retry transient failures internally:

- network timeout
- connection reset
- HTTP 5xx

It must not retry these automatically:

- risk control
- login required
- invalid binding token
- invalid or stale context
- invalid xsec token
- parser/schema mismatch

Those errors should be returned to the caller with stable `code`, `retryable`,
and `action` fields.

## Public vs Admin Surface

Normal applications call `/v1/...`.

Only destructive management operations such as force-unbind and session destroy
live under `/admin/v1/...` and should be protected by deployment-level
authentication or a separate gateway policy. Normal applications must not call
admin endpoints directly.
