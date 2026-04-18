from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import IssueViewSet, MagazineViewSet

router = SimpleRouter()
router.register(
    r'magazines/(?P<magazine_slug>[-\w]+)/issues',
    IssueViewSet,
    basename='magazine-issues'
)

router.register(
    r'issues',
    IssueViewSet,
    basename='issues'
)

router.register(
    r'magazines',
    MagazineViewSet,
    basename='magazines'
)

urlpatterns = [
    path('api/<str:version>/issues/recent/', IssueViewSet.as_view({'get': 'list'})),
    path('api/<str:version>/magazines/', MagazineViewSet.as_view({'get': 'list'})),
    path('api/<str:version>/', include(router.urls)),
]