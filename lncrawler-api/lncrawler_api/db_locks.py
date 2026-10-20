"""Row locks shared by the merge, import and model code.

This module imports nothing from the app: the model modules use it, and
``services`` and ``utils`` both import heavy modules that import the models.
"""


def lock_pks(model, pks):
    """Row-lock ``model`` rows in one statement, ordered by pk, and return the pks still present.

    Callers must be inside a transaction. Taking every lock a unit of work needs
    in one sorted call keeps two concurrent units from waiting on each other.
    """
    pks = sorted(set(pks))
    if not pks:
        return set()
    return set(
        model.objects.select_for_update()
        .filter(pk__in=pks)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
