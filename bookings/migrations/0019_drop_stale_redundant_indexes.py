"""Drop two indexes that only exist on databases migrated through old states.

`reference` and `order_id` were each `db_index=True` before they were
`unique=True`. Django built a plain index for the first state, and when
uniqueness was added later it built the unique index alongside without removing
the now-redundant one -- `AlterField` does not clean up an index it did not
create in that step. A database built from scratch today gets only the unique
index, so this is drift that exists on migrated databases and nowhere else.

Written as introspection rather than `RunSQL` for two reasons: the index names
carry Django's hash suffix and are not guaranteed identical across databases,
and a fresh database has nothing to drop, so the operation has to be a no-op
there rather than an error.

Irreversible by choice. The reverse would be to recreate an index that is
redundant by definition, which is not a state worth being able to return to.
"""

from django.db import migrations


#: (table, column) pairs whose plain index is fully covered by a unique index
#: on the same single column.
_REDUNDANT = [
    ("bookings_appointment", "reference"),
    ("bookings_appointment", "order_id"),
]


def _drop_redundant_indexes(apps, schema_editor):
    connection = schema_editor.connection

    for table, column in _REDUNDANT:
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, table)

        for name, spec in constraints.items():
            covers_only_this_column = spec.get("columns") == [column]
            is_plain_index = (
                spec.get("index")
                and not spec.get("unique")
                and not spec.get("primary_key")
                and not spec.get("foreign_key")
            )
            if covers_only_this_column and is_plain_index:
                schema_editor.execute(
                    schema_editor.sql_delete_index
                    % {
                        "table": schema_editor.quote_name(table),
                        "name": schema_editor.quote_name(name),
                    }
                )


class Migration(migrations.Migration):

    # MySQL cannot roll back DDL, so Django refuses to run schema changes inside
    # the transaction `RunPython` would otherwise open. Dropping an index is
    # safe to leave half-done anyway: the loop is idempotent, and re-running it
    # skips whatever the previous attempt already removed.
    atomic = False

    dependencies = [
        ("bookings", "0018_alter_appointment_clerk_user_id_and_more"),
    ]

    operations = [
        migrations.RunPython(
            _drop_redundant_indexes,
            migrations.RunPython.noop,
        ),
    ]
