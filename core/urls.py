from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedDefaultRouter

from .views import IssueViewSet, MagazineViewSet, IssueSectionViewSet, SectionViewSet

router = DefaultRouter()
router.register(r'magazines', MagazineViewSet, basename='magazines')
router.register(r'issues', IssueViewSet, basename='issues')
router.register(r'sections', SectionViewSet, basename='sections')

magazines_router = NestedDefaultRouter(router, r'magazines', lookup='magazine')
magazines_router.register(r'issues', IssueViewSet, basename='magazine-issues')

issues_router = NestedDefaultRouter(router, r'issues', lookup='issue')
issues_router.register(r'sections', IssueSectionViewSet, basename='issue-sections')

urlpatterns = [
    path('api/<str:version>/issues/recent/', IssueViewSet.as_view({'get': 'list'})),
    path('api/<str:version>/', include(router.urls)),
    path('api/<str:version>/', include(magazines_router.urls)),
    path('api/<str:version>/', include(issues_router.urls)),
]