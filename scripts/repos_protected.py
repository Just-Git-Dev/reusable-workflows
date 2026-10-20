"""Protected service accounts, shared by the GCP planners F5-F7 (docs/repos-register.md §5 item 9).

`repo-admin` is ALWAYS protected: the name is hard-coded here and no flag, input or register key
can lift it. A caller may protect more accounts (the CI accounts the access-provisioning config
declares) with `--protected-service-accounts`, a comma or newline separated list that is MERGED
with `repo-admin`, never replacing it.
"""

import re

ALWAYS = ("repo-admin",)


def parse(text):
    """A comma / newline / whitespace separated list -> a set holding ALWAYS plus its entries."""
    items = [t for t in re.split(r"[,\s]+", text or "") if t]
    return set(ALWAYS) | set(items)


def add_argument(ap):
    ap.add_argument("--protected-service-accounts", default="",
                    help="comma or newline list of service account names to protect, merged with repo-admin")
