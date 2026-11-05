# v2 Event Mapping

| Source | Source event | Normalized action |
|---|---|---|
| Generic JSON/CSV | `login` / `success` | `logon_success` |
| Generic JSON/CSV | `failed_login` / `authentication_failure` | `logon_failure` |
| Generic JSON/CSV | `privilege_grant` | `privilege_granted` |
| Generic JSON/CSV | `read` | `file_read` |
| Generic JSON/CSV | `write` | `file_write` |
| Generic JSON/CSV | `delete` | `file_delete` |
| Generic JSON/CSV | `visit` / `http` | `web_visit` |
| Linux auth | Accepted password | `logon_success` |
| Linux auth | Failed password / authentication failure | `logon_failure` |
| Linux auth | `sudo:` | `privilege_used` |
| Apache/Nginx | Combined access record | `web_visit` |
| Windows XML | 4624 | `logon_success` |
| Windows XML | 4625 | `logon_failure` |
| Windows XML | 4672 | `privilege_granted` |
| Windows XML | 4663 | `file_read` |
| Windows XML | 4720 | `account_created` |
| Windows XML | 4726 | `account_deleted` |
| Firefox history | `moz_historyvisits` row | `web_visit` |

Unrecognized source actions and Windows event IDs normalize to `unknown` and
retain their raw source data.
