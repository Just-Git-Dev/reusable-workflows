"""Who owns a service account's policy, shared by the GCP planners F5-F7 (docs/repos-register.md §5
item 9, ruling 21 "one writer per service-account policy").

The name says who writes the account's IAM policy, so neither side ever has to read the other:
`^[a-z][a-z0-9-]*-deployer$` is the project's (F5 links it, F6 creates and updates it); every other
account in the GCP project belongs to the access-provisioning side (or to Google). That includes
`repo-admin` itself, which fails the suffix rule by name, so no list has to be kept in step.

There is no caller-supplied protected list: the `--protected-service-accounts` flag and the workflows'
`protected_service_accounts` input were removed (owner ruling 2026-10-20; no release had shipped them).
"""

import re

PROJECT_SA_RE = re.compile(r"[a-z][a-z0-9-]*-deployer")     # matched with fullmatch: `$` accepts a trailing newline


def is_project_sa(name):
    """True when `name` is a service account the project (this repo's automation) may manage."""
    return isinstance(name, str) and PROJECT_SA_RE.fullmatch(name) is not None
