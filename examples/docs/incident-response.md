# Kaikeel Handbook Lite: Incident Response

*Fictional sample document for the DocQA demo.*

An incident is any unplanned event that breaks or degrades something a client relies on.

## Severity levels

| Level | Meaning | First response | Update cadence |
|---|---|---|---|
| SEV1 | Production is down or data is at risk | 30 minutes | every hour |
| SEV2 | A major feature is broken, workaround exists | 4 hours | twice a day |
| SEV3 | Minor bug or cosmetic issue | 1 business day | when fixed |

## Roles

- **Incident commander**: owns the incident, decides priorities and keeps the timeline.
- **Fixer**: investigates and applies the fix. For small incidents one person may hold both
  roles.
- **Communicator**: sends status updates to the client at the agreed cadence.

## Steps

1. Acknowledge the report and assign a severity level.
2. Stabilise first: roll back the last release if it is the likely cause.
3. Find and fix the root cause, with a regression test.
4. Confirm with the client that service is restored.

## Postmortem

Every SEV1 and SEV2 incident gets a blameless postmortem within three business days. The
postmortem lists the timeline, the root cause, what went well, and at most three action
items, each with an owner and a due date. Postmortems are stored in the knowledge base.
