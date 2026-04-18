from django.http import Http404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Issue, Magazine, IssueSection
from .serializers import IssueListSerializer, MagazineSerializer, IssueReaderSerializer


class IssueViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Issue.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()

        magazine_slug = self.kwargs.get('magazine_slug')
        if magazine_slug:
            qs = qs.filter(magazine__slug=magazine_slug)

        if self.action == 'retrieve':
            qs = qs.prefetch_related(
                'renders',
                'issue_sections__section',
                'issue_sections__segments',
            )

        return qs

    def get_object(self):
        queryset = self.get_queryset()

        magazine_slug = self.kwargs.get('magazine_slug')
        lookup_value = self.kwargs.get(self.lookup_field or 'pk')

        # lookup por edição quando estiver dentro de magazine
        if magazine_slug:
            try:
                return queryset.get(
                    magazine__slug=magazine_slug,
                    edition__iexact=lookup_value
                )
            except Issue.DoesNotExist:
                raise Http404("Issue not found")

        return super().get_object()

    def get_serializer_class(self):
        if self.action == 'list':
            return IssueListSerializer
        return IssueReaderSerializer

    @action(detail=True, methods=['get'], url_path='pages/(?P<page>[^/.]+)')
    def page_detail(self, request, *args, **kwargs):
        issue = self.get_object()
        try:
            page = int(kwargs['page'])
        except ValueError:
            return Response({"error": "Invalid page"}, status=400)

        render = issue.pages.filter(order=page).first()

        issue_section = IssueSection.objects.filter(
            issue=issue,
            segments__start_page__lte=page,
            segments__end_page__gte=page
        ).distinct().first()

        return Response({
            "page": page,
            "image": render.image.url if render else None,
            "section": {
                "id": issue_section.id,
                "name": issue_section.section.name,
                "has_text": bool(issue_section.text_content)
            } if issue_section else None
        })

class MagazineViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Magazine.objects.all()
    serializer_class = MagazineSerializer