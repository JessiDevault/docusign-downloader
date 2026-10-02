# DocuSign downloader

A Docker application for an existing Linux Docker host managed by Portainer. It downloads selected signed documents from completed envelopes, excludes Certificates of Completion, and tracks jobs and downloads in SQLite. The browser interface provides previews, manual runs, live progress on refresh, and persistent recent job history. Scheduled jobs run automatically after configuration.

## Deploy in your existing Portainer

Do not deploy deploy/portainer.compose.yaml: that older optional file installs Portainer itself. The application stack is **compose.yaml** at the repository root.

### 1. Choose persistent storage in Portainer

Keep HOST_DATA_ROOT at `/srv/docker/docusign-downloader` unless your Docker host uses another dedicated application-data location. The stack creates config, data, downloads, and logs beneath that path during deployment. No host terminal commands are needed.

A small initialize container sets folder ownership to PUID/PGID and permissions to 700, then exits successfully. The downloader starts only after initialization succeeds. An exited initialize container with exit code 0 is expected. If initialization fails, open its logs in Portainer. Keep PUID/PGID unchanged after first deployment: initialization does not recursively change existing databases or downloaded files. Use a dedicated path, not an existing shared folder.

This stack requires a Docker Standalone environment with Compose dependency support. It is not a Docker Swarm stack.

Mounts use absolute host paths outside the Git checkout. Replacing the container preserves these folders. Back up all four folders; stop the application while copying its SQLite database. Run only one application instance against this database.

### 2. Wait for the GitHub Actions image build

The Test and publish container workflow validates tests and Compose, builds the image, and publishes:

- ghcr.io/jessidevault/docusign-downloader:main
- ghcr.io/jessidevault/docusign-downloader:sha-COMMIT_SHA

For reproducible deployments, set IMAGE_TAG to a published sha tag. The main tag is a moving development tag. Private GitHub repositories and private container images require separate authentication in Portainer.

### 3. Configure registry and repository access

In Portainer, add a GitHub Container Registry entry for ghcr.io with your GitHub username and a credential with package-read access. Enter credentials directly in Portainer, never in this repository or chat. Git repository authentication also needs access to this private repository. Verify organization policies and token authorization if access is denied.

### 4. Add the application stack

Choose Stacks > Add stack > Repository:

| Field | Value |
| --- | --- |
| Stack name | docusign-downloader |
| Repository URL | https://github.com/JessiDevault/docusign-downloader.git |
| Repository reference | refs/heads/main |
| Compose path | compose.yaml |

Enable repository authentication. Select your GHCR registry. Add these environment variables using deploy/app.env.example as the reference:

| Variable | Value or purpose |
| --- | --- |
| HOST_DATA_ROOT | /srv/docker/docusign-downloader |
| APP_PASSWORD | A unique password of at least 16 characters |
| APP_USERNAME | admin, or your preferred login |
| BIND_ADDRESS | Docker host private IP for LAN access, or 127.0.0.1 behind an HTTPS proxy |
| APP_PORT | 8088 |
| PUID / PGID | 10001 / 10001; match host folder ownership |
| IMAGE_TAG | main initially, or a published sha tag |
| DOCUSIGN_AUTH_HOST | account-d.docusign.com for demo; account.docusign.com for production |
| DOCUSIGN_CLIENT_ID | Integration key |
| DOCUSIGN_USER_ID | API user GUID |
| DOCUSIGN_ACCOUNT_ID | Account GUID accessible to that user |
| AUTO_ENABLED | false until a test download has been checked |
| AUTO_START_DATE | First historical completion date, YYYY-MM-DD |
| AUTO_INTERVAL_SECONDS | 86400 for daily jobs; minimum 300 |
| DOCUMENT_NAME_PATTERN | Optional case-insensitive filename regular expression |

Portainer's IP 10.102.0.10 is not necessarily the Docker host IP. Use the actual Docker host interface for BIND_ADDRESS. The app uses HTTP and Basic authentication; place it behind your HTTPS reverse proxy for routine use, or access it through an SSH tunnel. The unauthenticated /health endpoint reports only process availability.

Click Deploy the stack. With automatic jobs disabled, the interface starts even before DocuSign credentials are ready.

### 5. Configure DocuSign JWT authentication

Create/configure a DocuSign integration using JWT, generate an RSA key pair, and grant the user consent for signature and impersonation. Save the private key directly on the host as:

```text
/srv/docker/docusign-downloader/config/private-key.pem
```

To place the key using Portainer, open Containers > the downloader container > Console. Choose `/bin/sh`, use its default application user (10001), and connect. Enter `umask 077`, then `cat > /config/private-key.pem`, paste the PEM key including its BEGIN/END lines, and press Ctrl-D to finish. Do not paste the key into GitHub, stack YAML, or chat. The configuration mount is writable for this setup step; the image/root filesystem remains read-only. The created key is readable only by its owner. No Docker CLI or host terminal is required.

Access tokens are held in memory and refreshed automatically. Production access requires the integration to be approved/promoted for production; a demo integration cannot download production contracts. The account ID is checked against OAuth userinfo and the API base URI is discovered from DocuSign.

See https://developers.docusign.com/platform/auth/jwt-get-token/ for the JWT setup and consent requirements. Do not put private keys or tokens in GitHub.

### 6. Verify before enabling automatic jobs

Open the application through your HTTPS proxy or tunnel. Preview a known completion date with limit 1. Review the inventory CSV in the data folder, then run a one-envelope download and open the PDF. Progress to 5, 25, and 100 envelopes before a full archive run.

Without a filter, only envelopes with one content document are selected. Multiple-document envelopes require a filename filter. A filter can select multiple documents; confirm it matches only the contracts you want. No selection is recorded as needing attention rather than silently counted as success. Wet-signed attachments are excluded from this default selection and require a separately validated rule.

Preview never downloads PDFs. Downloads use temporary files, validate PDF header/end marker, atomically rename the file, and record envelope ID + document ID + checksum in SQLite. Existing files are skipped only if their stored checksum and PDF markers still match. Failed/partial downloads can be retried by running the range again.

### 7. Enable automatic jobs

Set AUTO_START_DATE and DOCUMENT_NAME_PATTERN, then set AUTO_ENABLED=true and redeploy the stack. The first automatic job starts immediately; later jobs run at AUTO_INTERVAL_SECONDS. Job history and schedule due time persist in SQLite across restarts. Successful complete scans advance the completion-date window with a one-day overlap. Failed or ambiguous scans keep the earlier window for retry. Interrupted jobs are marked interrupted on restart and downloads resume on the next run. Changing the historical start date after a successful backfill does not rewind the stored window; use a manual range for earlier backfills.

Dates and schedule timestamps use UTC. One job runs at a time. Automatic scans have a 100000-envelope ceiling; larger archives need a separate pagination/backfill strategy. Rerun the same range to recover failed documents. Inventory CSVs and logs accumulate and should be retained/rotated according to your storage policy.

### 8. Pull updates from GitHub

Keep Compose changes in GitHub and host-specific values in Portainer environment variables. Git-backed stacks can pull/redeploy repository changes; available polling/webhook automation depends on the installed Portainer edition. When using the moving main image tag, select image re-pull during update so the new published image is retrieved. A Git check that runs before image publication can retrieve the old image: wait for Actions to succeed and then pull/redeploy, or use a published sha tag for a controlled update. Do not detach the stack from Git if you want continued Git-backed updates.

https://docs.portainer.io/user/docker/stacks/add
https://docs.portainer.io/user/docker/stacks/edit

## Current verification scope

Local automated tests cover document/certificate selection, preview inventory, duplicate avoidance across runner recreation, corrupted-file recovery, invalid PDF retry, date ranges, and durable job history. Live DocuSign authentication/downloads, the Linux container, registry access, Portainer deployment, and Git update behavior must still be verified in your environment. /health does not validate DocuSign connectivity.
