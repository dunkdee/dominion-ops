# Similarweb Trial Private Storage

This directory defines the expected local-only storage layout for the seven-day capture window.

```text
raw/          original permitted exports
normalized/   validated Dominion records
manifests/    export inventory and completeness reports
```

The directories are ignored by Git. Do not commit account credentials, API keys, raw Similarweb exports, screenshots containing account details, personal data, health-sensitive data, or licensed platform datasets.

Only schemas, synthetic fixtures, policies, and non-sensitive hashes belong in the repository.
