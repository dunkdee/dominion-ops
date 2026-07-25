# Dominion Video Studio Media Policy

**Policy state:** candidate for Five Council review  
**Applies to:** portrait images, voice recordings, source videos, scripts containing personal information, generated media, and associated consent/approval records.

## 1. Authorized subject rule

Dominion Video Studio may process a person's likeness or voice only when a complete consent record confirms:

- the subject is identified;
- likeness use is authorized;
- voice use is authorized;
- the uploader has the required rights to the submitted media;
- the requested purpose and release scope are recorded.

The first controlled release is limited to the Human Overseer's own portrait and voice. Third-party subjects, public figures, customers, minors, deceased persons, and synthetic impersonation targets require a separate governed release request and evidence appropriate to the jurisdiction and use.

## 2. Purpose limitation

Media may be used only for the approved project and its recorded output format. It may not be reused for model training, biometric identification, advertising, external publication, resale, or a different subject/project without a new authorization.

## 3. Storage boundary

- Personal media and generated outputs must remain on approved persistent storage outside container images and source-control history.
- Git commits, pull-request attachments, routine CI artifacts, logs, issue comments, and model registries must not contain personal media.
- Secret references and worker tokens must remain in protected runtime configuration with mode `0600` or an equivalent secret store.
- Public object storage is prohibited for the first controlled release.

## 4. Access control

- Human Overseer: may approve, review, export, reject, delete, or revoke use.
- Approved operator service: may read/write only the project media required for an authorized job.
- Worker: receives time-bounded access to only the assets in its claimed job and may upload only the resulting job output.
- Council and audit processes: receive hashes, metadata, test results, and sanitized evidence; they do not receive the personal media unless the Human Overseer separately authorizes that review.

All other access is denied by default.

## 5. Retention

Default first-release retention:

- rejected or failed temporary worker copies: delete immediately when the job ends;
- temporary render workspaces: delete on completion or failure;
- uploaded source media: retain until the Human Overseer deletes the project or revokes consent;
- generated outputs: retain until approved export or project deletion;
- consent, approval, deletion, and audit records: retain after media deletion as non-media evidence, subject to applicable legal requirements;
- operational logs: retain only sanitized identifiers, timestamps, status, durations, and error summaries; never raw media or secret values.

A future multi-tenant product must define customer-facing retention periods before activation.

## 6. Deletion and revocation

A deletion or consent-revocation operation must:

1. stop queued or running jobs when technically possible;
2. prevent new worker claims for the affected project;
3. remove source media, temporary copies, and generated outputs from active storage;
4. record what was deleted, when, by which authorized actor, and any backup-retention exception;
5. preserve only non-media evidence needed to prove the deletion and governance decision.

Backups containing deleted media require a defined expiration and must not be restored into active processing except for documented disaster recovery.

## 7. Output control

Generated media remains private and review-only until the Human Overseer records approval. External publication, customer delivery, advertising use, monetization, or distribution requires a separately governed release when applicable.

## 8. Prohibited uses

- cloning without documented authorization;
- impersonation intended to deceive, defraud, harass, or evade verification;
- unauthorized political, legal, financial, medical, or identity representations;
- removal or concealment of required disclosure in contexts where disclosure is legally or contractually required;
- ingestion of scraped personal media or unverified model/checkpoint sources;
- using personal media to train or fine-tune a model without a separate explicit authorization.

## 9. Incident response

Suspected unauthorized access, disclosure, impersonation, secret exposure, or retention failure triggers immediate job suspension, token rotation, evidence preservation, containment, Human Overseer notice, and Security/Law Council review before reactivation.

## 10. Release gate

Production activation remains blocked until tests prove consent enforcement, unauthorized worker rejection, storage permissions, temporary-copy cleanup, project deletion/revocation behavior, rollback, and private output review.
