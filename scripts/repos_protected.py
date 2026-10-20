"""Who owns a service account's policy, shared by the GCP planners F5-F7 (docs/repos-register.md §5
item 9, ruling 21 "one writer per service-account policy").

The name says who writes the account's IAM policy, so neither side ever has to read the other:
`^[a-z][a-z0-9-]*-deployer$` is the project's (F5 links it, F6 creates and updates it); every other
account in the GCP project belongs to the access-provisioning side (or to Google). That includes
`repo-admin` itself, which fails the suffix rule by name, so no list has to be kept in step.

The `--protected-service-accounts` flag (and the workflows' `protected_service_accounts` input) is a
DEPRECATED NO-OP: it is still accepted so existing callers do not break, and it is ignored.
"""

import re

PROJECT_SA_RE = re.compile(r"^[a-z][a-z0-9-]*-deployer$")


def is_project_sa(name):
    """True when `name` is a service account the project (this repo's automation) may manage."""
    return isinstance(name, str) and PROJECT_SA_RE.match(name) is not None


def add_argument(ap):
    ap.add_argument("--protected-service-accounts", default="",
                    help="DEPRECATED no-op (accepted and ignored): the `-deployer` suffix rule decides")
