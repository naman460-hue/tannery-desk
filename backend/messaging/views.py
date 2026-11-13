from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from common.files import file_response
from common.validators import clean_filename, validate_document_upload
from notifications.services import notify
from orders.views import orders_for
from rfqs.views import rfq_queryset_for

from .models import Message


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.CharField(source="sender.role", read_only=True)
    mine = serializers.SerializerMethodField()
    attachment_url = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ("id", "sender_name", "sender_role", "mine", "body", "attachment_url", "attachment_name", "created_at")
        read_only_fields = fields

    def get_sender_name(self, obj):
        if obj.sender.role == "ADMIN":
            return "Tannery Desk team"
        return obj.sender.company_name or obj.sender.name

    def get_mine(self, obj):
        return obj.sender_id == self.context["request"].user.pk

    def get_attachment_url(self, obj):
        return f"/api/messages/{obj.pk}/attachment/" if obj.attachment else None


def resolve_thread(request, data):
    """Works out (client_user, factory_user, rfq, order) for the thread asked about, checking the caller's access."""
    user = request.user
    order_id, rfq_id = data.get("order"), data.get("rfq")
    if order_id:
        order = orders_for(user).select_related("client", "factory__user").filter(pk=order_id).first()
        if not order:
            raise NotFound()
        return order.client, order.factory.user, None, order
    if rfq_id:
        rfq = rfq_queryset_for(user).filter(pk=rfq_id).select_related("client").first()
        if not rfq:
            raise NotFound()
        if user.role == "FACTORY":
            factory_user = user
        else:
            factory_user = User.objects.filter(pk=data.get("factory"), role="FACTORY",
                                               factory_profile__rfq_matches__rfq=rfq).first()
            if not factory_user:
                raise ValidationError({"factory": ["Please choose a factory that has this RFQ."]})
        return rfq.client, factory_user, rfq, None
    raise ValidationError({"detail": ["Please say which RFQ or order this message is about."]})


class MessageListCreateView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        client, factory_user, rfq, order = resolve_thread(request, request.query_params)
        qs = Message.objects.filter(client=client, factory=factory_user).select_related("sender")
        qs = qs.filter(order=order) if order else qs.filter(rfq=rfq, order__isnull=True)
        return Response(MessageSerializer(qs, many=True, context={"request": request}).data)

    def post(self, request):
        client, factory_user, rfq, order = resolve_thread(request, request.data)
        body = (request.data.get("body") or "").strip()
        upload = request.FILES.get("attachment")
        if not body and not upload:
            raise ValidationError({"body": ["Please type a message."]})
        if len(body) > 2000:
            raise ValidationError({"body": ["Please keep messages under 2000 characters."]})
        message = Message(client=client, factory=factory_user, rfq=rfq, order=order, sender=request.user, body=body)
        if upload:
            try:
                validate_document_upload(upload)
            except Exception as exc:
                raise ValidationError({"attachment": list(getattr(exc, "messages", [str(exc)]))})
            message.attachment = upload
            message.attachment_name = clean_filename(upload.name)
        message.save()
        ref = order.number if order else rfq.number
        link = f"#/orders/{order.pk}" if order else f"#/rfqs/{rfq.pk}"
        for recipient in {client, factory_user} - {request.user}:
            notify(recipient, "New message", f"{ref}: {body[:100] or 'Attachment received'}", "MESSAGE", link)
        return Response(MessageSerializer(message, context={"request": request}).data, status=status.HTTP_201_CREATED)


class MessageAttachmentView(APIView):
    def get(self, request, pk):
        message = Message.objects.filter(pk=pk).first()
        if not message or not message.attachment:
            raise NotFound()
        user = request.user
        if user.role != "ADMIN" and user.pk not in (message.client_id, message.factory_id):
            raise NotFound()
        return file_response(message.attachment, message.attachment_name)
