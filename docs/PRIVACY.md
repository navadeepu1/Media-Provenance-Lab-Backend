# Privacy and retention policy

Media Provenance Lab processes uploaded media only to generate the requested
provenance report. The offline profile stores uploads, derived heatmaps, jobs,
and reports under the configured data directory. It does not send files to an
external provider unless an operator explicitly enables a provider integration.

The default retention period is 30 days for reports and one day for job upload
files. Operators may reduce these values through environment configuration.
Expired records are removed by scheduled cleanup, and a report deletion request
is available through the API. Production operators must verify that
object-storage versions, backups, caches, and derived artifacts follow the same
deletion policy.

The application does not intentionally return GPS coordinates, but uploaded
files may contain sensitive metadata. Users should remove sensitive media unless
they understand the configured storage and retention settings.

The local profile has no authentication and must not be exposed to the public
internet. Production deployment requires authenticated report ownership,
private object storage, encrypted transport, access-controlled audit logs,
backup retention, and a documented data-subject deletion process.
