from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from common.permissions import IsAdminRole
from core.activity import log_activity
from notifications.services import notify_admins

from .models import Role, User
from .serializers import (
    AdminUserSerializer, ChangePasswordSerializer, LoginSerializer, PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer, ProfileUpdateSerializer, RegisterSerializer, UserSerializer, _password_errors,
)


def _set_refresh_cookie(response, token):
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME, token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True, secure=not settings.DEBUG, samesite="Lax", path=settings.REFRESH_COOKIE_PATH,
    )


def _issue_tokens(user, status_code=200):
    refresh = RefreshToken.for_user(user)
    response = Response({"access": str(refresh.access_token), "user": UserSerializer(user).data}, status=status_code)
    _set_refresh_cookie(response, str(refresh))
    return response


def _require_xhr(request):
    """Cookie-based endpoints need a custom header, which cross-site forms cannot send (CSRF defence)."""
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        raise PermissionDenied("Invalid request.")


class _Public(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class RegisterView(_Public):
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if user.role == Role.FACTORY:
            notify_admins("New factory registration", f"{user.company_name} registered and is waiting for verification.",
                          "FACTORY", "#/admin/factories")
        log_activity(user, f"New {user.role.lower()} registered: {user.company_name or user.name}")
        return _issue_tokens(user, status.HTTP_201_CREATED)


class LoginView(_Public):
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.filter(email__iexact=data["email"]).first()
        if not user or not user.check_password(data["password"]):
            return Response({"detail": "Incorrect email or password."}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.is_active:
            return Response({"detail": "This account is suspended. Please contact Tannery Desk support."},
                            status=status.HTTP_403_FORBIDDEN)
        portal = data.get("portal")
        if portal and user.role != portal:
            return Response({"detail": "This account cannot sign in here."}, status=status.HTTP_403_FORBIDDEN)
        return _issue_tokens(user)


class RefreshView(_Public):
    throttle_scope = "auth"

    def post(self, request):
        _require_xhr(request)
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw:
            return Response(status=status.HTTP_204_NO_CONTENT)
        try:
            old = RefreshToken(raw)
            user = User.objects.get(pk=old["user_id"], is_active=True)
            old.blacklist()
        except (TokenError, User.DoesNotExist, KeyError):
            response = Response(status=status.HTTP_204_NO_CONTENT)
            response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH)
            return response
        return _issue_tokens(user)


class LogoutView(_Public):
    def post(self, request):
        _require_xhr(request)
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response({"detail": "You have been signed out."})
        response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH)
        return response


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(UserSerializer(serializer.save()).data)


class ChangePasswordView(APIView):
    throttle_scope = "auth"

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        return Response({"detail": "Your password has been changed."})


class PasswordResetRequestView(_Public):
    throttle_scope = "auth"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"], is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL}/#/reset-password?uid={uid}&token={token}"
            send_mail(
                "Reset your Tannery Desk password",
                f"Hello {user.name},\n\nUse this link to choose a new password:\n{link}\n\n"
                "If you did not ask for this, you can ignore this email.",
                settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True,
            )
        # Same answer whether or not the email exists, so accounts cannot be discovered.
        return Response({"detail": "If an account exists for that email, we have sent a link to reset the password."})


class PasswordResetConfirmView(_Public):
    throttle_scope = "auth"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(data["uid"])), is_active=True)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            user = None
        if not user or not default_token_generator.check_token(user, data["token"]):
            raise ValidationError({"token": ["This reset link is invalid or has expired. Please request a new one."]})
        errors = _password_errors(data["new_password"], user)
        if errors:
            raise ValidationError({"new_password": errors})
        user.set_password(data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return Response({"detail": "Your password has been reset. You can now sign in."})


class AdminUserViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin: list, and suspend / reactivate users."""

    permission_classes = [IsAdminRole]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.all().select_related("factory_profile").order_by("-created_at")
        params = self.request.query_params
        if params.get("role") in Role.values:
            qs = qs.filter(role=params["role"])
        if params.get("active") in ("true", "false"):
            qs = qs.filter(is_active=params["active"] == "true")
        q = params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(company_name__icontains=q))
        return qs

    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        user = self.get_object()
        if user.pk == request.user.pk or user.role == Role.ADMIN:
            raise ValidationError({"detail": ["Admin accounts cannot be suspended here."]})
        active = request.data.get("is_active")
        if not isinstance(active, bool):
            raise ValidationError({"is_active": ["Please choose suspend or reactivate."]})
        user.is_active = active
        user.save(update_fields=["is_active", "updated_at"])
        log_activity(request.user, f"{'Reactivated' if active else 'Suspended'} user {user.email}")
        return Response(AdminUserSerializer(user).data)
