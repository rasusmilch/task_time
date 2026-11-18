"""Complete isolated schema-5 semantics on caller-owned snapshots; no opener."""
from dataclasses import dataclass

from . import schema5_profiles as schema
from .project_services import CandidateProjectContext
from .schema4_evidence import verify_selected_transaction


class Context:
    authority = schema
    administrative_operations = schema.ADMINISTRATIVE_OPERATIONS

    @staticmethod
    def verify_administration(c, receipts):
        from .administration import verify_project_history
        facts = {name: schema._rows(c, name) for name, in c.execute(
            "SELECT name FROM sqlite_schema WHERE type='table'")}
        dataset = facts['dataset_meta'][0]['dataset_id']
        verify_project_history(facts['projects'], facts['tasks'], facts['committed_requests'],
                               dataset, facts=facts, policy=CandidateProjectContext(dataset, 5))


@dataclass(frozen=True)
class SemanticVerification:
    schema_version: int = 5
    structural_verified: bool = True
    administrative_history_verified: bool = True
    semantic_verified: bool = True
    ordinary_startup_permitted: bool = False


def verify_transaction(c):
    """Read-only complete verification inside the caller's active transaction.

    No BEGIN/COMMIT/ROLLBACK, connection factory, worker or runtime registration.
    The structural-only foundation retains its separate result and meaning.
    """
    verify_selected_transaction(c, Context)
    return SemanticVerification()
