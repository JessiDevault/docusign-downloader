# DocuSign Downloader deployment project

## Confirmed requirements
- Download completed signed contract PDFs and exclude Certificates of Completion.
- Support 1,000+ contracts, duplicate protection, resumable downloads, and success/failure logs.
- Publish the application source and deployment templates in GitHub.
- Deploy through Portainer with a disposable application container.
- Keep configuration, database, downloads, and logs in host folders outside the container.
- Configure Git-backed deployment updates.
- Establish and verify a working Portainer instance.

## Current evidence
The local workspace contains Git metadata only. No application code is present. The private GitHub repository is https://github.com/JessiDevault/docusign-downloader. Docker, Git, and gh were not found on the current command path. The shared conversation ends at DocuSign API setup; authentication and downloads have not been verified.

## Proposed deployment design
Build application images in GitHub Actions and publish to GitHub Container Registry. Store Compose deployment templates in the same repository. Portainer deploys the Git-backed stack and checks for changes. Image updates require an explicit image version or digest change in the stack; updating a template alone does not build an image.

Mount separate absolute host directories into /config, /data, /downloads, and /logs. Keep these directories outside the Git checkout so stack updates cannot replace persistent state. Store credentials only in the mounted configuration folder; exclude credentials, tokens, databases, and downloaded contracts from source control and image builds. Persist resumable download state in SQLite under /data. Use envelope ID plus document ID as the unique download identity.

## Implementation and verification checklist
- [ ] Identify any existing application source and migration data.
- [ ] Confirm Docker host and access method.
- [x] Confirm GitHub owner, repository, and visibility: JessiDevault/docusign-downloader (private).
- [ ] Clarify what templates must auto-update.
- [ ] Establish Docker and Portainer on the selected host.
- [ ] Implement authentication and verify one completed envelope.
- [ ] Implement contract selection, pagination, retries, and resumable download state.
- [ ] Add Dockerfile, Compose stack, image build workflow, and deployment instructions.
- [ ] Publish repository and image.
- [ ] Deploy through Portainer and verify application behavior.
- [ ] Recreate container and verify configuration, database, and files survive.
- [ ] Verify a Git template/image update reaches the deployed stack.
- [ ] Validate progressive bulk runs before the full archive download.

## Pending decisions
Deployment host, template meaning, and location of existing source are awaiting user input. The user will make deployment changes in Portainer.
