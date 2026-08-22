"""Search endpoint — extension beyond spec §60 (decision F-004).

Exposes RetrievalService so hybrid retrieval is exercisable end-to-end
and reusable by chat/enrichment in later phases.
"""
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.retrieval.retrieval import RetrievalService


class SearchSerializer(serializers.Serializer):
    query = serializers.CharField(min_length=1, max_length=500)
    subject = serializers.UUIDField(required=False, allow_null=True)
    top_k = serializers.IntegerField(min_value=1, max_value=50, required=False, default=8)
    include_reference = serializers.BooleanField(required=False, default=True)


from shared.throttles import LiveScopedRateThrottle


class SearchView(APIView):
    throttle_classes = [LiveScopedRateThrottle]
    throttle_scope = "ai"
    def post(self, request):
        serializer = SearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        subject = None
        if data.get("subject"):
            from apps.subjects.models import Subject

            try:
                subject = Subject.objects.get(pk=data["subject"], profile__user=request.user)
            except Subject.DoesNotExist:
                from shared.exceptions import ValidationError

                raise ValidationError("Unknown subject for this user.")

        evidence = RetrievalService.search(
            request.user,
            data["query"],
            subject=subject,
            top_k=data["top_k"],
            include_reference=data["include_reference"],
        )
        return Response(
            {"query": data["query"], "count": len(evidence), "results": [e.as_dict() for e in evidence]},
            status=status.HTTP_200_OK,
        )
