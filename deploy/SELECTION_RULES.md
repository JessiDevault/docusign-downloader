# Download selection
Only completed envelopes can be previewed or downloaded. Date ranges refer to completion dates in UTC.
The optional Envelope sender field loads account users when focused. Type a name or email and choose a populated entry. Names, emails and user IDs distinguish duplicate names. Clear the field to include all accessible senders. Unselected text is rejected.
Sender and template filters must both match. Template IDs remain comma-separated, with any selected template matching. Blank includes all templates. The envelope limit counts scanned envelopes before local template matching.
Automatic jobs use TEMPLATE_IDS and optional SENDER_USER_ID (the selected sender's DocuSign user GUID). DOCUSIGN_USER_ID remains the identity used to authenticate. Changing filters resets the automatic scan cursor. Leave AUTO_ENABLED=false during testing.
The integration user must be permitted to list account users and access the chosen sender's envelopes. Selecting a sender grants no additional access.
Existing completed downloads keep their original duplicate detection. Certificates are excluded and ambiguous document sets require a filename filter.
