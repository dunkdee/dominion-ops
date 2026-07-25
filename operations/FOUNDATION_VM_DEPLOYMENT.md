# Foundation VM Governed Deployment

## Authority

Production deployment is initiated manually by the Human Overseer through GitHub Actions. A merge to `main` does not itself authorize deployment.

## Required sequence

1. Validate the requested commit exists on `main`.
2. Run constitutional and control-plane validation in GitHub Actions.
3. Connect to `foundation-vm` using the production environment's protected secrets.
4. Verify repository identity, available disk space, Docker availability, and a clean deploy target.
5. Preserve the current commit as the rollback target.
6. Fetch the requested commit and check it out in detached state.
7. Run governance validators on the VM before changing services.
8. Rebuild and start only through the repository Compose definition.
9. Verify required containers and localhost health endpoints.
10. On any failure, restore the previous commit and rebuild the previous release.
11. Record the requested commit, prior commit, result, and rollback status in the Actions log.

## Prohibited behavior

- Automatic production deployment on every push.
- Reading, collecting, merging, printing, or rewriting unrelated environment files.
- Printing secret values or raw environment files.
- Deploying a commit that is not reachable from `origin/main`.
- Continuing after failed health verification.
- Deleting the previous release before the new release passes verification.
- Deploying directly from an unreviewed feature branch.

## GitHub configuration required

Create or retain a protected GitHub Environment named `foundation-vm-production` containing:

- `VM_HOST`
- `VM_USER`
- `VM_SSH_KEY`

Configure the environment to require the Human Overseer's approval before deployment. Repository workflows receive only read access unless a specific reviewed task requires more.

## Rollback

Rollback is automatic when deployment or verification fails. The workflow checks out the recorded prior commit and runs the same Compose build/start command. A failed rollback is a critical incident and must be handled under `operations/INCIDENT_RESPONSE.md`.
