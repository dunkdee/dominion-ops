# Dominion Strategizer

This directory contains the exact secret-scanned application source associated with the currently ready Cloud Run revision recorded by Dominion provenance repair issue #145.

## Verified identity

- Cloud Run service: `dominion-strategizer`
- Region: `us-central1`
- Ready revision: `dominion-strategizer-00003-8t9`
- Image digest: `sha256:ecd699e505cb37ec909ca5ce067469aeb0a468c788923cf0289efeafe939a620`
- Cloud Build ID: `d3c5442d-ce7b-470d-be58-b387121a55e1`
- Immutable build-source object: `gs://run-sources-dominion-ascendant-us-central1/services/dominion-strategizer/1774114093.985325-303349ab55804befa307771c2e6fce99.zip#1774114096084639`
- Source archive SHA-256: `d45182d745add4e6551600c285f2055807accc8de0923e33ddd693a44033b435`
- Source archive bytes: `6763703`
- Secret scan: `PASS` across all four allowlisted source files, with zero findings
- Health: `GET /health` returned HTTP `200` on 2026-08-11

The source was recovered copy-only from the immutable Cloud Run build-source generation. No service, revision, image, IAM policy, environment value, or Wix resource was changed.

## Routes

- `GET /health`
- `POST /strategize` with JSON body `{ "idea": "..." }`

## Governance hold

This source commit is provenance repair only. It does not authorize a build, deployment, restart, traffic change, secret access, or production mutation. Deployment material belongs in `dunkdee/dominion-infra`.
