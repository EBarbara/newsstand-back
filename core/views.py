from django.http import Http404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from decouple import config
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status

from core.services import process_cbz_file

def get_recent_count():
    return config('ISSUES_RECENT_COUNT', default=10, cast=int)

from .models import Issue, Magazine, IssueSection, Section
from .serializers import (
    IssueListSerializer,
    IssueReaderSerializer,
    IssueSectionWriteSerializer,
    IssueSectionSerializer,
    MagazineSerializer,
    SectionSerializer,
)


class IssueViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Issue.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()

        qs = qs.select_related('magazine')
        if self.action in ['list', 'recent']:
            qs = qs.prefetch_related('renders')

        # As identified in debug logs: 'magazine_magazine_slug'
        magazine_slug = self.kwargs.get('magazine_magazine_slug')
        
        if magazine_slug:
            qs = qs.filter(magazine__slug=magazine_slug)

        if self.action == 'retrieve':
            qs = qs.prefetch_related(
                'issue_sections__section',
                'issue_sections__segments',
            )

        return qs

    def get_object(self):
        queryset = self.get_queryset()
        
        magazine_slug = self.kwargs.get('magazine_magazine_slug')
        lookup_value = self.kwargs.get('pk')

        if magazine_slug and lookup_value:
            # Try lookup by edition first
            try:
                obj = queryset.get(
                    magazine__slug=magazine_slug,
                    edition__iexact=lookup_value
                )
                self.check_object_permissions(self.request, obj)
                return obj
            except Issue.DoesNotExist:
                # Fallback to ID
                if lookup_value.isdigit():
                    try:
                        obj = queryset.get(pk=lookup_value)
                        self.check_object_permissions(self.request, obj)
                        return obj
                    except (Issue.DoesNotExist, ValueError):
                        pass
                
                raise Http404(f"Issue {lookup_value} not found for magazine {magazine_slug}")

        return super().get_object()

    def get_serializer_class(self):
        if self.action in ['list', 'recent']:
            return IssueListSerializer
        return IssueReaderSerializer

    @action(detail=False, methods=['get'])
    def recent(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        count = get_recent_count()
        queryset = queryset.order_by('-publishing_date')[:count]

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def import_cbz(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"error": "No file provided. Field must be named 'file'."}, status=status.HTTP_400_BAD_REQUEST)
        
        magazine_slug = request.data.get('magazine')
        edition = request.data.get('edition')
        publishing_date = request.data.get('date')

        try:
            issue = process_cbz_file(
                file_obj=file_obj,
                filename=file_obj.name,
                magazine_slug=magazine_slug,
                edition=edition,
                publishing_date=publishing_date
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Failed to process CBZ: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = self.get_serializer(issue)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='pages/(?P<page>[^/.]+)')
    def page_detail(self, request, *args, **kwargs):
        issue = self.get_object()
        try:
            page = int(kwargs['page'])
        except ValueError:
            return Response({"error": "Invalid page"}, status=400)

        render = issue.renders.filter(order=page).first()

        sections = IssueSection.objects.filter(
            issue=issue,
            segments__start_page__lte=page,
            segments__end_page__gte=page
        ).distinct()

        sections = list(sections[:2])

        if len(sections) > 1:
            return Response(
                {"error": "Multiple sections found for page. Data inconsistency."},
                status=500
            )

        issue_section = sections[0] if sections else None

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
    lookup_field = 'slug'
    lookup_url_kwarg = 'magazine_slug'

class SectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Section.objects.all()
    serializer_class = SectionSerializer

class IssueSectionViewSet(viewsets.ModelViewSet):

    def get_queryset(self):
        return IssueSection.objects.filter(
            issue_id=self.kwargs['issue_pk']
        ).select_related('section').prefetch_related('segments')

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return IssueSectionSerializer
        return IssueSectionWriteSerializer

    def perform_create(self, serializer):
        serializer.save(issue_id=self.kwargs['issue_pk'])
