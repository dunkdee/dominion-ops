# Nemotron Reactivation Candidate — Release Notes

Status: REVIEW CANDIDATE — not production proof.

This branch converts Nemotron from a historical containment hold to a governed active service contract, hardens its listener to loopback only, adds a bounded exact-SHA activation lane with automatic rollback, and updates the read-only runtime observer so it expects the newly authorized state.

Production activation remains blocked until the exact PR head passes technical validation, the Founder authorization is bound to that head, and the Five Council returns FINAL_RELEASE_APPROVED for the same release request. The activation workflow then requires the exact merged main SHA and Founder actor/triggering actor before touching the VM.

No firewall opening, public listener, model download, credential change, external publication, money movement, live trading, Oracle activation, or unrelated service restart is included.
