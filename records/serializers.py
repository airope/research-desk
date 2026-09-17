from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    CandidatePair,
    CanonicalPublication,
    ImportFailure,
    ImportRun,
    MatchProposal,
    ReviewDecision,
    SourceRecord,
    SourceRecordVersion,
)


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceRecordVersion
        fields = "__all__"


class RecordSerializer(serializers.ModelSerializer):
    current_version = VersionSerializer(read_only=True)

    class Meta:
        model = SourceRecord
        fields = "__all__"


class ProposalSerializer(serializers.ModelSerializer):
    left_version = VersionSerializer(read_only=True)
    right_version = VersionSerializer(read_only=True)

    class Meta:
        model = MatchProposal
        fields = "__all__"


class DecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewDecision
        fields = "__all__"


class PairSerializer(serializers.ModelSerializer):
    left = RecordSerializer(read_only=True)
    right = RecordSerializer(read_only=True)
    proposal = serializers.SerializerMethodField()
    decisions = DecisionSerializer(many=True, read_only=True)

    @extend_schema_field(ProposalSerializer(allow_null=True))
    def get_proposal(self, obj):
        proposal = next(iter(obj.proposals.all()), None)
        return ProposalSerializer(proposal).data if proposal else None

    class Meta:
        model = CandidatePair
        fields = "__all__"


class PublicationSerializer(serializers.ModelSerializer):
    records = RecordSerializer(many=True, read_only=True)

    class Meta:
        model = CanonicalPublication
        fields = "__all__"


class DecisionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["accept", "reject", "defer"])
    reason = serializers.CharField(max_length=2000, allow_blank=True, default="")
    expected_revision = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=128)


class WithdrawInput(serializers.Serializer):
    reason = serializers.CharField(max_length=2000, allow_blank=False)
    expected_revision = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=128)


class ImportFailureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportFailure
        fields = ["id", "external_id", "code", "message", "attempts", "retryable", "resolved"]


class ImportRunSerializer(serializers.ModelSerializer):
    failures = ImportFailureSerializer(many=True, read_only=True)

    class Meta:
        model = ImportRun
        fields = [
            "id",
            "provider",
            "profile",
            "status",
            "counters",
            "cursor",
            "created_at",
            "updated_at",
            "error",
            "lease_expires_at",
            "started_at",
            "finished_at",
            "failures",
        ]
