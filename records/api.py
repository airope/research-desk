import uuid

from django.db.models import Case, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler

from .models import CandidatePair, CanonicalPublication, MatchProposal, ReviewDecision, SourceRecord
from .serializers import (
    DecisionInput,
    DecisionSerializer,
    ImportRunSerializer,
    PairSerializer,
    PublicationSerializer,
    RecordSerializer,
    VersionSerializer,
    WithdrawInput,
)
from .services import DomainError, decide, withdraw, withdrawal_preview


def can_write(user, role="curator"):
    return user.is_authenticated and (user.is_staff or user.groups.filter(name=role).exists())


class CuratorAccess(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or can_write(request.user)


class OperatorAccess(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or can_write(request.user, "operator")


def api_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        response = Response({"detail": str(exc)}, status=exc.status)
        code = exc.code
    else:
        response = exception_handler(exc, context)
        code = getattr(exc, "default_code", "invalid_request")
    if response is not None:
        request = context.get("request")
        detail = response.data
        response.data = {
            "code": code,
            "message": str(detail.get("detail", "The request could not be completed."))
            if isinstance(detail, dict)
            else "The request could not be completed.",
            "fields": detail if isinstance(detail, dict) and "detail" not in detail else {},
            "request_id": getattr(request, "request_id", str(uuid.uuid4())),
        }
    return response


class Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        raw = request.query_params.get("page_size", "20")
        if not raw.isdigit() or not 1 <= int(raw) <= 100:
            raise ValidationError({"page_size": "Choose an integer from 1 to 100."})
        return super().paginate_queryset(queryset, request, view)


def pair_queryset():
    return (
        CandidatePair.objects.select_related("left__current_version", "right__current_version")
        .prefetch_related("proposals__left_version", "proposals__right_version", "decisions")
        .annotate(
            latest_score=Subquery(
                MatchProposal.objects.filter(pair_id=OuterRef("pk"))
                .order_by("-created_at")
                .values("ranking_score")[:1]
            ),
            review_priority=Case(
                When(
                    state__in=["pending", "review", "needs_reassessment", "insufficient_evidence"],
                    then=Value(0),
                ),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        .order_by("review_priority", F("latest_score").desc(nulls_last=True), "-updated_at", "id")
    )


def filter_pairs(queryset, params):
    state = params.get("state", "")
    source = params.get("source", "")
    conflict = params.get("conflict", "")
    if state:
        if state not in [
            "pending",
            "review",
            "accepted",
            "rejected",
            "deferred",
            "needs_reassessment",
            "insufficient_evidence",
        ]:
            raise ValidationError({"state": "Unknown review state."})
        queryset = queryset.filter(state=state)
    if source:
        if source not in ["crossref", "openalex"]:
            raise ValidationError({"source": "Choose crossref or openalex."})
        queryset = queryset.filter(Q(left__provider=source) | Q(right__provider=source))
    if conflict:
        if conflict not in ["true", "false"]:
            raise ValidationError({"conflict": "Choose true or false."})
        # DOI disagreement is a stable, directly inspectable contradiction.
        conflicts = Q(left__doi__gt="") & Q(right__doi__gt="") & ~Q(left__doi=F("right__doi"))
        queryset = queryset.filter(conflicts) if conflict == "true" else queryset.exclude(conflicts)
    return queryset


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                "state",
                str,
                enum=[
                    "pending",
                    "review",
                    "insufficient_evidence",
                    "needs_reassessment",
                    "accepted",
                    "rejected",
                    "deferred",
                ],
            ),
            OpenApiParameter("source", str, enum=["crossref", "openalex"]),
            OpenApiParameter(
                "conflict",
                str,
                enum=["true", "false"],
                description="Whether source DOI values are both present and disagree.",
            ),
        ]
    )
)
class CandidateList(generics.ListAPIView):
    serializer_class = PairSerializer
    pagination_class = Pagination

    def get_queryset(self):
        return filter_pairs(pair_queryset(), self.request.query_params)


class CandidateDetail(generics.RetrieveAPIView):
    serializer_class = PairSerializer
    queryset = pair_queryset()


class DecisionCreate(APIView):
    permission_classes = [CuratorAccess]

    @extend_schema(
        request=DecisionInput,
        responses={201: DecisionSerializer},
        examples=[
            OpenApiExample(
                "Human decision",
                value={
                    "action": "accept",
                    "reason": "Same DOI and compatible edition",
                    "expected_revision": 1,
                    "idempotency_key": "curator-action-001",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request, pk):
        get_object_or_404(CandidatePair, pk=pk)
        data = DecisionInput(data=request.data)
        data.is_valid(raise_exception=True)
        result = decide(pk, actor=request.user.get_username(), **data.validated_data)
        return Response(DecisionSerializer(result).data, status=status.HTTP_201_CREATED)


class DecisionWithdraw(APIView):
    permission_classes = [CuratorAccess]

    @extend_schema(responses=dict)
    def get(self, request, pk):
        get_object_or_404(ReviewDecision, pk=pk)
        return Response(withdrawal_preview(pk))

    @extend_schema(request=WithdrawInput, responses={201: DecisionSerializer})
    def post(self, request, pk):
        get_object_or_404(ReviewDecision, pk=pk)
        data = WithdrawInput(data=request.data)
        data.is_valid(raise_exception=True)
        result = withdraw(pk, actor=request.user.get_username(), **data.validated_data)
        return Response(DecisionSerializer(result).data, status=201)


class RecordDetail(generics.RetrieveAPIView):
    serializer_class = RecordSerializer
    queryset = SourceRecord.objects.select_related("current_version")


class RecordVersions(generics.ListAPIView):
    serializer_class = VersionSerializer
    pagination_class = Pagination

    def get_queryset(self):
        return get_object_or_404(SourceRecord, pk=self.kwargs["pk"]).versions.all()


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Title or DOI search; at most 200 characters.")
        ]
    )
)
class PublicationList(generics.ListAPIView):
    serializer_class = PublicationSerializer
    pagination_class = Pagination

    def get_queryset(self):
        queryset = (
            CanonicalPublication.objects.filter(state="active")
            .prefetch_related("records__current_version")
            .order_by("-updated_at")
        )
        query = self.request.query_params.get("q", "").strip()
        if len(query) > 200:
            raise ValidationError({"q": "Search is limited to 200 characters."})
        if query:
            queryset = queryset.filter(
                Q(records__doi__icontains=query) | Q(records__title_key__icontains=query)
            ).distinct()
        return queryset


class PublicationDetail(generics.RetrieveAPIView):
    serializer_class = PublicationSerializer
    queryset = CanonicalPublication.objects.prefetch_related("records__current_version")


class PublicationHistory(generics.ListAPIView):
    serializer_class = DecisionSerializer
    pagination_class = Pagination

    def get_queryset(self):
        publication = get_object_or_404(CanonicalPublication, pk=self.kwargs["pk"])
        ids = publication.memberships.values_list("record_id", flat=True)
        return (
            ReviewDecision.objects.filter(Q(pair__left_id__in=ids) | Q(pair__right_id__in=ids))
            .distinct()
            .order_by("-created_at")
        )


class ImportInput(serializers.Serializer):
    provider = serializers.ChoiceField(choices=["crossref", "openalex"])
    profile = serializers.ChoiceField(choices=["demo"])
    idempotency_key = serializers.CharField(max_length=128)


class ImportCreate(APIView):
    permission_classes = [OperatorAccess]

    @extend_schema(request=ImportInput, responses={202: ImportRunSerializer})
    def post(self, request):
        from .ingestion import ImportConflict, create_import

        data = ImportInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            run = create_import(
                data.validated_data["provider"],
                {"fixture": "demo", "page_size": 20, "max_records": 100},
                data.validated_data["idempotency_key"],
            )
        except ImportConflict as exc:
            raise DomainError("idempotency_conflict", str(exc)) from exc
        return Response(import_data(run), status=202)


def import_data(run):
    return ImportRunSerializer(run).data


class ImportDetail(APIView):
    @extend_schema(responses=ImportRunSerializer)
    def get(self, request, pk):
        from .models import ImportRun

        return Response(import_data(get_object_or_404(ImportRun, pk=pk)))


class ImportRetry(APIView):
    permission_classes = [OperatorAccess]

    @extend_schema(request=None, responses={202: ImportRunSerializer})
    def post(self, request, pk):
        from .ingestion import retry_run
        from .models import ImportRun

        get_object_or_404(ImportRun, pk=pk)
        try:
            run = retry_run(pk)
        except ValueError as exc:
            raise DomainError("retry_conflict", str(exc)) from exc
        return Response(import_data(run), status=202)
