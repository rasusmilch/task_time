"""Explicit database policy; one production owner, no alternate store or writer."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaPolicy:
    version: int

    def statements(self):
        if self.version == 3:
            from .sqlite_store import schema_statements
        else:
            from .schema_profiles import schema_statements
        return schema_statements()

    def receipt_class(self, operation):
        if self.version == 3:
            from .records import receipt_class
            return receipt_class(operation)
        from .schema_profiles import ADMINISTRATIVE_OPERATIONS
        return 'administrative' if operation in ADMINISTRATIVE_OPERATIONS else 'protected'

    def verify(self, c, *, complete=True):
        from .sqlite_store import SQLiteStore, APPLICATION_ID, UnsupportedSchemaLayout
        if self.version == 3:
            return SQLiteStore._verify_complete(c) if complete else SQLiteStore._verify(c)
        if (c.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                or c.execute('PRAGMA user_version').fetchone()[0] != self.version):
            raise ValueError(f'Incompatible Chronicle dataset: require schema {self.version}; originals are retained. No migration/import is available.')
        from . import schema_profiles
        from .schema4_evidence import verify_transaction
        try:
            schema_profiles.verify_schema(c)
        except ValueError as exc:
            raise UnsupportedSchemaLayout(str(exc)) from exc
        return verify_transaction(c)


LEGACY_SCHEMA3 = SchemaPolicy(3)
CURRENT_SCHEMA4 = SchemaPolicy(4)


def policy_for(version):
    if type(version) is not int or version not in (3, 4):
        raise ValueError('An explicit supported schema policy is required')
    return LEGACY_SCHEMA3 if version == 3 else CURRENT_SCHEMA4
