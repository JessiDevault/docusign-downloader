# Downloads on SMB through Portainer

Use `portainer-smb-stack.yml` when the share is not already mounted on the Linux host. Docker's local volume driver mounts `//10.1.10.4/docusign` as `/downloads`. Configuration, SQLite data, and logs retain their existing local bind mounts. The initialization container does not change the remote share's ownership or permissions.

1. Keep automatic jobs disabled and wait for any running job to finish.
2. In Portainer, edit the existing `docusign-downloader` stack and replace its YAML with `portainer-smb-stack.yml`.
3. Preserve all existing environment variables. Add `SMB_USERNAME`, `SMB_PASSWORD`, and `SMB_DOMAIN` as described in `portainer-smb.env.example`. Keep `APP_PORT=8098`.
4. Update the stack. Docker creates and mounts a CIFS-backed volume automatically; no separate manual image pull or volume creation is required.
5. Confirm the downloader is healthy. In its console, run the write check below, then run a manual Download job and check the share from Windows at `\\10.1.10.4\docusign`.

```sh
python -c "from pathlib import Path; import tempfile; p=Path('/downloads'); f=tempfile.TemporaryFile(dir=p); f.write(b'SMB write check'); f.flush(); f.close(); print('SMB write check passed')"
```

The Docker host must support CIFS and reach the share on TCP 445. SMB 3.0 is requested. The share account needs permission to read, create, rename, and delete files. Volume driver options, including credentials, are visible to Docker/Portainer administrators. Do not publish filled-in credentials. Passwords containing commas require a different credential mechanism, such as a host mount using a protected credentials file.

Existing PDFs remain in `/srv/docker/docusign-downloader/downloads`; this change does not move them. The database remains local. The downloader checks file existence and hashes, so a previously downloaded document missing from the share is downloaded there again when included in a new job. Confirm that result before enabling automatic jobs.

Docker volume options are saved when the volume is first created. Later changes to credentials/options may require recreating the mount volume while the stack is stopped. Do not remove the local data or config folders.

If the SMB share is already mounted on the host, use its actual local mount path as the downloader's `/downloads` bind source instead, with `create_host_path: false`. Exclude that mount from the initialization container to avoid changing shared ownership. Do not use the `smb://` URL as a bind source.
