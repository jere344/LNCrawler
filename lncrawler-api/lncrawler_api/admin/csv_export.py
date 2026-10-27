import csv

from django.contrib import admin
from django.http import StreamingHttpResponse
from django.utils import timezone

# Never written to the CSV (e.g. the user password hash).
EXCLUDED_FIELDS = {"password"}


class _Echo:
    """Pseudo-buffer for csv.writer: returns each row instead of storing it."""

    def write(self, value):
        return value


@admin.action(description="Export selected to CSV")
def export_as_csv(modeladmin, request, queryset):
    """Site-wide action: every concrete field of the selected rows (FKs as ids)."""
    opts = modeladmin.model._meta
    fields = [f for f in opts.concrete_fields if f.name not in EXCLUDED_FIELDS]
    writer = csv.writer(_Echo())

    def rows():
        yield "﻿"  # BOM so Excel reads UTF-8
        yield writer.writerow([f.attname for f in fields])
        for obj in queryset.iterator(chunk_size=2000):
            yield writer.writerow([getattr(obj, f.attname) for f in fields])

    filename = f"{opts.model_name}_{timezone.now():%Y%m%d_%H%M%S}.csv"
    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


admin.site.add_action(export_as_csv)
