"""H2 (J1): create the DRAFT release for the owner's existing tag, per repo.

This flow creates NO tag and NO ref: the owner pushed the annotated tag, and the pre-check
(validate.validate_manifest) re-asserts, for every listed repo and before the first write,
that it still exists, is annotated and peels to the listed sha, along with CI and the rest.
A bad second repo therefore cannot leave a first repo with an orphan draft. Every write is
recorded the moment it lands: DraftsError.created maps each touched repo to its release id
(int) or to a sentence saying the request's outcome is unknown. The CLI prints that map on
failure too. No re-entry: an existing Release of that name fails validation, and versions of a
failed run are burned.
"""

from __future__ import annotations

import ci
import gh
import validate


class DraftsError(Exception):
    def __init__(self, failures, created):
        super().__init__("; ".join(failures))
        self.failures = failures
        self.created = created


def precheck(reader, cfg, entries):
    """Every read-only check that guards the first write (validate, tag re-assertion, CI).
    -> list of failures; empty means drafts may be created. Takes a Reader only, so a rehearsal
    (`drafts --check-only`) can run it with no write token at all."""
    failures = validate.validate_manifest(reader, cfg, entries)
    ci_failures, examined = ci.check(reader, cfg, entries)
    failures += ci_failures
    if examined == 0:
        failures.append("CI check examined 0 workflows; refusing to proceed on no evidence")
    return failures


def create_drafts(reader, writer, cfg, entries):
    failures = precheck(reader, cfg, entries)
    if failures:
        raise DraftsError(failures, {})
    created = {}
    for e in entries:
        try:
            rel = writer.create_draft(cfg.owner, e.repo, e.version)
            created[e.repo] = rel["id"]
        except (gh.GitHubError, gh.Refused) as ex:
            if isinstance(ex, gh.GitHubError) and ex.status == 0:
                # transport error / timeout: the POST may have landed. Never under-state.
                created[e.repo] = "unknown — release request sent, response lost"
            raise DraftsError([f"{e.repo}: {ex}"], created) from ex
        except (KeyError, TypeError) as ex:
            # a 2xx release response we cannot read: the draft probably exists
            created[e.repo] = (f"unknown — release request sent, response unreadable "
                               f"({type(ex).__name__}: {ex})")
            raise DraftsError([f"{e.repo}: malformed GitHub response: {ex!r}"], created) from ex
    return created
