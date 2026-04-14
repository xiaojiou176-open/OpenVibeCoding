# Security Policy

## Reporting A Vulnerability

- Do not open a public issue or pull request for a suspected security problem.
- Current live private reporting path: the public repository
  `xiaojiou176-open/OpenVibeCoding` has GitHub private vulnerability
  reporting enabled. Submit reports through the advisory form at
  `https://github.com/xiaojiou176-open/OpenVibeCoding/security/advisories/new`.
- If that form is unavailable, do not disclose details publicly. This
  repository still does not publish a second verified fallback private
  reporting channel, so none should be assumed by reporters.
- Maintainer follow-up tail: before calling the security reporting surface
  fully closed, publish or verify a non-public fallback path outside public
  issues and pull requests.
- Wait for maintainer acknowledgement through the advisory flow before sharing
  any details publicly.

## In Scope

Please report issues involving:

- credential handling or secret exposure
- authorization, approval, or replay surfaces
- browser profile, cookie, or automation isolation
- telemetry, evidence, and log redaction
- CI, release, or supply-chain integrity

## What To Include

- affected path or feature
- reproduction steps
- expected and actual behavior
- impact assessment
- any temporary mitigation you tested

## What Not To Include

- real secrets, cookies, tokens, or private data
- exploit details in public channels
- large unrelated refactors mixed with a security report

## Response Expectations

- security reports are triaged on a best-effort basis
- no SLA or bounty program is promised
- coordinated disclosure is preferred
- branch protection and other GitHub security controls should be treated as
  separate governance checks; they do not replace the private reporting path

Thank you for helping keep OpenVibeCoding safer for contributors and users.
