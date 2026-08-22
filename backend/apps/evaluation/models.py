"""AI evaluation models (architecture §26).

EvalRun records one evaluation pass: which dataset file/version, which
kind (retrieval / citation), and the computed metrics. Datasets live as
versioned JSON files outside production data.
"""
import uuid

from django.db import models


class EvalRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=32)  # retrieval | citation
    dataset_name = models.CharField(max_length=255)
    metrics = models.JSONField(default=dict)
    case_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"evalrun {self.kind} {self.pk} ({self.case_count} cases)"
