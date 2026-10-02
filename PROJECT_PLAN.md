# Project status

## Goal
Deploy a disposable DocuSign downloader through the existing Linux Docker/Portainer environment at 10.102.0.10, backed by the private GitHub repository JessiDevault/docusign-downloader. Use persistent host folders and automatic jobs with a viewing interface.

## Implemented
- Dockerfile and root compose.yaml for the application.
- GitHub Actions test/build/publish workflow for GHCR.
- JWT OAuth authentication, account verification, and automatic token refresh.
- Completed-envelope pagination and completion-date filtering in UTC.
- Document selection, certificate exclusion, preview inventory, PDF downloads.
- SQLite job/download history, checksum duplicate protection, atomic file writes.
- Browser login, job history, manual previews/downloads, automatic recurring jobs.
- Host bind mounts under /srv/docker/docusign-downloader.
- Setup, credential, update, and verification instructions in README.md.

## Local validation
Six automated tests pass: selection, UTC ranges, preview, resume/corruption recovery, invalid-PDF retry, and durable job history. Application syntax validated.

## Remaining verification
- [ ] GitHub Actions tests and container image publication.
- [ ] Private repository and registry authentication in Portainer.
- [ ] Create host directories and set ownership.
- [ ] Deploy root compose.yaml and open the interface.
- [ ] Configure DocuSign integration, JWT consent, and private key on host.
- [ ] Verify one contract, then progressive batches.
- [ ] Enable automatic schedule and verify a job runs.
- [ ] Recreate container and verify data/configuration survival.
- [ ] Verify Git-backed stack/image update behavior in installed Portainer edition.

The user manages changes in Portainer. Existing deploy/portainer.compose.yaml is an optional Portainer installer and is not the downloader stack.
