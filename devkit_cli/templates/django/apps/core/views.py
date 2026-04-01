"""Core Django app — views."""

from django.http import JsonResponse


def index(request):
    return JsonResponse({"message": "Welcome to {{project_name}}"})
