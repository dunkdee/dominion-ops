# Provenance Repair #145

Status: source and runtime provenance recovered; no deployment performed.

## Evidence chain

1. GitHub Actions run `31528551320` queried the current Cloud Run service and ready revision read-only.
2. Cloud Run identified Cloud Build `d3c5442d-ce7b-470d-be58-b387121a55e1` and one immutable GCS source object generation.
3. That exact object was copied to an ephemeral runner, byte/hash verified, traversal checked, allowlisted, and scanned for secret patterns.
4. The four resulting source files map to image digest `sha256:ecd699e505cb37ec909ca5ce067469aeb0a468c788923cf0289efeafe939a620`.
5. `GET /health` returned HTTP `200` without a production mutation.

Artifact evidence:

- Deployed-source artifact ID: `9115926741`
- Deployed-source artifact digest: `sha256:16885d32bab4c44384faf694b3fb3a285a1dc06b25023eb224f151d36aa7d6eb`
- Runtime artifact ID: `9115924159`
- Runtime artifact digest: `sha256:2231a517767c03d223308aa684a78a34d697f5954957993ec2c59903012cf4d0`

## VoltEdge disposition

The seven issue-#145 VoltEdge hashes were not found on the Foundation VM, and the laptop runner is denied access to both `C:\Users\Dell\buddy_core\voltedge` and the old Strategizer archive root. The acceptance criteria explicitly allow quarantine instead of uploading unverifiable source. They are therefore recorded in `voltedge-quarantine.json` as laptop-only experimental artifacts.

No ACL bypass, source upload, Wix write, registry edit, overlay application, V3 rerun, or Phase 5B action occurred.

## Remaining archive evidence

The governed laptop restore path is recorded, but its exact archive SHA-256 and byte count remain blocked by the current NTFS ACL. The deployed Cloud Run source archive has an independently verified immutable hash and byte count; it does not silently replace the older laptop archive record.
