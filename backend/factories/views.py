from django.db.models import Q
from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.files import file_response
from common.permissions import IsAdminRole, IsFactory
from core.activity import log_activity
from notifications.services import notify

from .models import FactoryDocument, FactoryProfile, Verification
from .serializers import FactoryDocumentSerializer, FactoryPrivateSerializer, FactoryPublicSerializer


def search_factories(qs, q):
    q = (q or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(city__icontains=q) | Q(state__icontains=q) | Q(description__icontains=q))
    return qs


class FactoryListView(generics.ListAPIView):
    """Public directory of verified factories."""

    permission_classes = [AllowAny]
    serializer_class = FactoryPublicSerializer

    def get_queryset(self):
        qs = FactoryProfile.objects.marketplace().prefetch_related("documents")
        return search_factories(qs, self.request.query_params.get("q")).order_by("-rating", "name")


class FactoryDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = FactoryPublicSerializer

    def get_queryset(self):
        return FactoryProfile.objects.marketplace().prefetch_related("documents")


class MyFactoryView(APIView):
    permission_classes = [IsFactory]

    def get(self, request):
        return Response(FactoryPrivateSerializer(request.user.factory_profile).data)

    def patch(self, request):
        serializer = FactoryPrivateSerializer(request.user.factory_profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MyDocumentsView(generics.ListCreateAPIView):
    permission_classes = [IsFactory]
    serializer_class = FactoryDocumentSerializer
    throttle_scope = "upload"

    def get_queryset(self):
        return FactoryDocument.objects.filter(factory=self.request.user.factory_profile)

    def perform_create(self, serializer):
        serializer.save(factory=self.request.user.factory_profile)


class MyDocumentDeleteView(generics.DestroyAPIView):
    permission_classes = [IsFactory]

    def get_queryset(self):
        return FactoryDocument.objects.filter(factory=self.request.user.factory_profile)

    def perform_destroy(self, instance):
        instance.file.delete(save=False)
        instance.delete()


class DocumentDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        doc = FactoryDocument.objects.select_related("factory__user").filter(pk=pk).first()
        if not doc:
            raise NotFound()
        user = request.user
        allowed = user.role == "ADMIN" or doc.factory.user_id == user.pk or (
            doc.factory.verification_status == Verification.VERIFIED and doc.kind == "CERTIFICATE")
        if not allowed:
            raise NotFound()
        return file_response(doc.file, doc.original_name)


class AdminFactoryListView(generics.ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = FactoryPrivateSerializer

    def get_queryset(self):
        qs = FactoryProfile.objects.select_related("user").prefetch_related("documents").order_by("-created_at")
        status_value = self.request.query_params.get("status")
        if status_value in Verification.values:
            qs = qs.filter(verification_status=status_value)
        return search_factories(qs, self.request.query_params.get("q"))


class AdminFactoryVerificationView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        profile = FactoryProfile.objects.select_related("user").filter(pk=pk).first()
        if not profile:
            raise NotFound()
        new_status = request.data.get("status")
        note = (request.data.get("note") or "").strip()[:300]
        if new_status not in Verification.values:
            raise ValidationError({"status": ["Please select a valid status."]})
        if new_status in (Verification.REJECTED, Verification.SUSPENDED) and not note:
            raise ValidationError({"note": ["Please give a short reason so the factory knows what to fix."]})
        profile.verification_status = new_status
        profile.verification_note = note
        profile.verified_at = timezone.now() if new_status == Verification.VERIFIED else None
        profile.save(update_fields=["verification_status", "verification_note", "verified_at", "updated_at"])
        messages = {
            Verification.VERIFIED: ("Your factory is verified", "You can now receive RFQs and send quotations."),
            Verification.REJECTED: ("Factory verification was not approved", note),
            Verification.SUSPENDED: ("Your factory has been suspended", note),
            Verification.PENDING: ("Your factory is back in review", "The Tannery Desk team is reviewing your profile."),
        }
        title, text = messages[new_status]
        notify(profile.user, title, text, "FACTORY", "#/factory/profile")
        log_activity(request.user, f"Set factory '{profile.name}' to {new_status}")
        return Response(FactoryPrivateSerializer(profile).data)
