# Kaikeel Handbook Lite: Delivery Process

*Fictional sample document for the DocQA demo. Kaikeel Handbook Lite describes an imaginary
software studio; the procedures are illustrative only.*

## Purpose

This page explains how a finished project is handed over to a client. The goal of the
handover is simple: the client can run, understand and maintain what we built without
needing to ask us anything.

## Before handover

A project is ready for handover only when all of the following are true:

1. Every acceptance criterion in the project brief is checked and linked to evidence
   (a test, a screenshot or a log excerpt).
2. The quality review is marked PASS by a reviewer who did not write the code.
3. The security review is marked PASS, including a secret scan of the full git history.
4. The README has been followed from a clean machine by someone other than the author.

## The handover package

Every delivery contains the same five items, in this order:

- **Source code** as a git repository or a zip archive built from the release tag.
- **README** with setup steps, configuration variables and how to run the tests.
- **CHANGELOG** describing what changed in this release.
- **Handover note**: a one-page summary of what was delivered, known limitations and the
  recommended next steps.
- **Credentials checklist**: a list of every account or key the client must create
  themselves. We never send live credentials by email or chat.

## Handover meeting

The handover meeting lasts at most 30 minutes. The delivery lead shares the screen, runs the
quick start from the README and answers questions. The meeting is recorded only if the client
agrees in writing beforehand.

## After handover

The project moves to the support phase. The warranty period starts on the day the client
confirms receipt of the handover package (see the warranty policy).
