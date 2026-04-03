from django.urls import path, include
from rest_framework import routers

from .views import IssueViewSet

router = routers.DefaultRouter()
router.register(r'issues', IssueViewSet, basename='api-issue')

urlpatterns = [
    path('api/v1/', include(router.urls)),
]