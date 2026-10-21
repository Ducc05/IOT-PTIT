from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers.auth import (
    AuthSessionSerializer,
    CurrentUserSerializer,
    CurrentUserUpdateSerializer,
    RegistrationSerializer,
)


class RegisterView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        request=RegistrationSerializer, responses={201: AuthSessionSerializer}
    )
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            AuthSessionSerializer.for_user(user).data, status=status.HTTP_201_CREATED
        )


class CurrentUserView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses=CurrentUserSerializer)
    def get(self, request):
        return Response(
            CurrentUserSerializer(request.user, context={"request": request}).data
        )

    @extend_schema(request=CurrentUserUpdateSerializer, responses=CurrentUserSerializer)
    def post(self, request):
        serializer = CurrentUserUpdateSerializer(request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(CurrentUserSerializer(user, context={"request": request}).data)
