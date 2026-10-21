from typing import ClassVar
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from core.serializers.common import StrictModelSerializer

User = get_user_model()


class RegistrationSerializer(StrictModelSerializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ("username", "email", "password", "password_confirm")

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        candidate = User(username=attrs["username"], email=attrs.get("email", ""))
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"username": "This username is already taken."}
            ) from exc


class CurrentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "full_name", "student_id", "avatar")
        read_only_fields = fields


class CurrentUserUpdateSerializer(StrictModelSerializer):
    email = serializers.EmailField(required=True, allow_blank=True)
    avatar = serializers.ImageField(required=False)

    class Meta:
        model = User
        fields = ("full_name", "student_id", "email", "avatar")
        extra_kwargs: ClassVar[dict[str, dict[str, bool]]] = {
            "full_name": {"required": True, "allow_blank": True},
            "student_id": {"required": True, "allow_blank": False, "allow_null": True},
        }

    def validate_avatar(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Ảnh đại diện không được vượt quá 5 MB.")
        extensions = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
        extension = extensions.get(value.image.format)
        if extension is None:
            raise serializers.ValidationError("Vui lòng chọn ảnh JPG, PNG hoặc WebP.")
        value.name = f"{uuid4().hex}.{extension}"
        return value

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"student_id": "This student ID is already in use."}
            ) from exc


class AuthSessionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    access = serializers.CharField()
    refresh = serializers.CharField()

    @classmethod
    def for_user(cls, user):
        if not user.is_active:
            raise serializers.ValidationError("Inactive accounts cannot sign in.")
        refresh = RefreshToken.for_user(user)
        return cls(
            {
                "id": user.pk,
                "username": user.username,
                "email": user.email,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        )
