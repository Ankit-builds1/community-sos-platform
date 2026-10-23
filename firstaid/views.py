from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from config.throttles import FirstAidThrottle

from .assistant import answer


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=500)


class FirstAidAskView(APIView):
    """POST /api/first-aid/ask/  {"question": "my father has chest pain"}"""
    throttle_classes = [FirstAidThrottle, UserRateThrottle]

    def post(self, request):
        data = AskSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(answer(data.validated_data["question"]))
