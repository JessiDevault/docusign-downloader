# Template and status selection

Manual Preview and Download use the same filters. Select current envelope statuses in the GUI and enter comma-separated template UUIDs copied from DocuSign. Multiple statuses are OR; multiple template IDs are OR; status and template filters are AND. Blank template IDs include all envelopes, including those created without a template. Completed remains the default status.

The downloader checks `/envelopes/{id}/templates` only when a template filter is set. It matches associated template IDs, not subject text or document names. Deleted/inaccessible associations are not inferred. API failures mark a job failed/needs attention rather than silently including the envelope. Template filtering adds an API request per scanned envelope, so use bounded dates and avoid frequent repeated scans.

Dates are inclusive UTC calendar dates. With Completed alone, they refer to completion time. When selecting any other status, they refer to the envelope's latest status change. Only the envelope's current status is matched, not its historical statuses. The envelope limit is a scan limit before template matching; a small limit may produce no matches even when later envelopes match.

Document selection remains separate: certificates are excluded, a document-name regex explicitly selects matching content documents, and without a regex only single-content-document envelopes are selected. Multi-document envelopes need a filter before downloading.

Non-completed documents are snapshots and may lack signatures. They receive status/timestamp filename suffixes and separate duplicate records so later completed downloads are not suppressed. Updates without an envelope status change are not detected as a new snapshot by this version.

Automatic jobs use these Portainer environment variables:

```env
ENVELOPE_STATUSES=completed
TEMPLATE_IDS=
```

Changing automatic filters starts a new scan cursor from AUTO_START_DATE; existing PDFs still use duplicate protection. Keep AUTO_ENABLED=false while testing. GUI defaults use these filters, but a manual job can choose different filters.

Demo acceptance: preview one matching and one nonmatching template, an envelope created without a template, and at least two statuses. Test a composite envelope with multiple associated templates. Verify UTC date boundaries. Download a sent snapshot, then complete that envelope and download its final PDF. Repeat each download to verify duplicate protection. Empty status selection or malformed template IDs must be rejected before starting a job.

Use the updated SMB YAML after its referenced image has been published. Preserve current Portainer credentials, APP_PORT=8098, and SMB variables. No production migration is part of this change.
