# DocuSign bulk downloader

Project under construction. No downloader application or production deployment exists yet. See PROJECT_PLAN.md for requirements and pending decisions.

## Portainer bootstrap

The deployment in deploy/portainer.compose.yaml targets a standalone Linux Docker engine or Docker Desktop running Linux containers. It is not a Windows-container or Swarm deployment.

1. Confirm the intended host and install Docker Engine with Compose using the vendor instructions for that host.
2. Create an absolute host directory for Portainer data, outside this repository. On Linux, for example: `sudo mkdir -p /srv/docker/portainer/data`.
3. Copy deploy/portainer.env.example to deploy/portainer.env and set PORTAINER_DATA_DIR to that directory. On Docker Desktop, use an absolute shared Windows path such as C:/docker/portainer/data.
4. Validate with `docker compose --env-file deploy/portainer.env -f deploy/portainer.compose.yaml config`.
5. Start with `docker compose --env-file deploy/portainer.env -f deploy/portainer.compose.yaml up -d`.
6. Open https://localhost:9443 on that host and complete the initial administrator setup. For a remote host, use an SSH tunnel (`ssh -L 9443:127.0.0.1:9443 user@host`) or set PORTAINER_BIND_ADDRESS to its private interface address before deployment.
7. Verify the local Docker environment appears and reports its containers in Portainer.

The Docker socket gives Portainer control of the Docker host. The UI defaults to loopback binding. Portainer uses a self-signed TLS certificate by default; browser certificate decisions require the user.

The host data directory holds Portainer settings and its database. Back it up before upgrading. The lts tag is mutable; record the deployed image digest when selecting the final deployment version. Replacing a container must reuse the same data path.

## Planned application storage

| Container path | Persistent host contents |
| --- | --- |
| /config | Application settings and OAuth credentials |
| /data | SQLite download history and resume state |
| /downloads | Signed contract PDFs |
| /logs | Success/failure logs |

Host paths will be absolute and outside the repository. Credentials and contract files are excluded from Git and Docker build contexts.

## Planned GitHub updates

GitHub Actions will build the downloader image into GitHub Container Registry. The application Compose file will reference a version or digest. Portainer will check the Git-backed stack for deployment changes; availability of automated Git updates must be checked against the installed Portainer edition. A code change needs a new image and a deployment image-reference change. This bootstrap stack does not yet configure application updates.

## Verification still required

The Compose file has not been validated by Docker or run on a host. Verify startup, login, host connectivity, backup/restore, and container recreation before declaring Portainer established. The application then needs authentication, document-selection validation, a small download run, persistence verification, and an end-to-end Git update test.

## References

- https://docs.portainer.io/start/install-ce/server/docker/linux
- https://docs.portainer.io/faqs/troubleshooting/stacks-deployments-and-updates/how-do-automatic-updates-for-stacks-applications-work
- https://docs.docker.com/engine/storage/bind-mounts/
