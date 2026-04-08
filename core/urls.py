from django.urls import path, include
from rest_framework import routers
from rest_framework.routers import SimpleRouter

from .views import IssueViewSet, PublicIssueViewSet, PublicMagazineViewSet

issue_list = IssueViewSet.as_view({'get': 'list'})
issue_detail = IssueViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})

router = SimpleRouter()
router.register(
    r'magazines/(?P<magazine_slug>[-\w]+)/issues',
    IssueViewSet,
    basename='magazine-issues'
)

urlpatterns = [
    path('api/<str:version>/', include(router.urls)),
    path('api/<str:version>/issues/recent/', PublicIssueViewSet.as_view({'get': 'list'})),
    path('api/<str:version>/magazines/', PublicMagazineViewSet.as_view({'get': 'list'})),
]