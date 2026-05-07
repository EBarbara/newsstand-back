from django.http import Http404
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from decouple import config
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework import status

from core.services import process_cbz_file

def get_recent_count():
    return config('ISSUES_RECENT_COUNT', default=10, cast=int)

from PIL import Image
from django.core.files.base import ContentFile
from django.db import models, transaction
from .models import Issue, Magazine, IssueSection, Section, RenderAsset, SectionSegment, Person, Credit, Tag
from .serializers import (
    IssueListSerializer,
    IssueReaderSerializer,
    IssueSectionWriteSerializer,
    IssueSectionSerializer,
    MagazineSerializer,
    SectionSerializer,
    PersonSerializer,
    PersonDetailSerializer,
    PersonCreditSerializer,
    TagSerializer,
)


class IssueViewSet(viewsets.ModelViewSet):
    queryset = Issue.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()

        qs = qs.select_related('magazine')
        if self.action in ['list', 'recent']:
            qs = qs.prefetch_related('renders', 'tags')

        # Tag filtering
        tag_slug = self.request.query_params.get('tag')
        if tag_slug:
            qs = qs.filter(tags__slug=tag_slug)
        
        # Tag exclusion (for "filter out" special editions)
        exclude_tag = self.request.query_params.get('exclude_tag')
        if exclude_tag:
            qs = qs.exclude(tags__slug=exclude_tag)

        # As identified in debug logs: 'magazine_magazine_slug'
        magazine_slug = self.kwargs.get('magazine_magazine_slug')
        
        if magazine_slug:
            qs = qs.filter(magazine__slug=magazine_slug)

        if self.action == 'retrieve':
            qs = qs.prefetch_related(
                'issue_sections__section',
                'issue_sections__segments',
                'tags'
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

    @action(detail=False, methods=['post'], parser_classes=[JSONParser])
    def create_empty(self, request, *args, **kwargs):
        magazine_slug = request.data.get('magazine')
        edition = request.data.get('edition')
        publishing_date = request.data.get('date')

        if not all([magazine_slug, edition, publishing_date]):
            return Response({"error": "magazine, edition and date are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            magazine = Magazine.objects.get(slug=magazine_slug)
        except Magazine.DoesNotExist:
            return Response({"error": f"Magazine {magazine_slug} not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            issue = Issue.objects.create(
                magazine=magazine,
                edition=edition,
                publishing_date=publishing_date,
            )
        except Exception as e:
            return Response({"error": f"Failed to create issue: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

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

    @action(detail=True, methods=['post'], url_path='upload-page')
    def upload_page(self, request, *args, **kwargs):
        issue = self.get_object()
        file = request.FILES.get('file')
        order = int(request.data.get('order', issue.renders.count() + 1))

        if not file:
            return Response({"error": "No file provided"}, status=400)

        with transaction.atomic():
            # Shift existing pages in reverse order to avoid unique constraint violations
            renders_to_shift = issue.renders.filter(order__gte=order).order_by('-order')
            for r in renders_to_shift:
                r.order += 1
                r.save()

            # Shift segments
            segments = SectionSegment.objects.filter(issue_section__issue=issue)
            for seg in segments:
                if seg.start_page >= order:
                    seg.start_page += 1
                    seg.end_page += 1
                    seg.save()
                elif seg.start_page < order <= seg.end_page:
                    seg.end_page += 1
                    seg.save()

            # Create new render
            img = Image.open(file)
            width, height = img.size
            
            render = RenderAsset.objects.create(
                issue=issue,
                order=order,
                width=width,
                height=height,
                image=file
            )

        return Response(IssueReaderSerializer(issue, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='replace-page/(?P<render_pk>[^/.]+)')
    def replace_page(self, request, render_pk=None, *args, **kwargs):
        issue = self.get_object()
        file = request.FILES.get('file')
        
        try:
            render = issue.renders.get(pk=render_pk)
        except RenderAsset.DoesNotExist:
            return Response({"error": "Page not found"}, status=404)

        if not file:
            return Response({"error": "No file provided"}, status=400)

        img = Image.open(file)
        render.width, render.height = img.size
        render.image = file
        render.save()

        return Response(IssueReaderSerializer(issue, context={'request': request}).data)

    @action(detail=True, methods=['delete'], url_path='delete-page/(?P<render_pk>[^/.]+)')
    def delete_page(self, request, render_pk=None, *args, **kwargs):
        issue = self.get_object()
        
        try:
            render = issue.renders.get(pk=render_pk)
        except RenderAsset.DoesNotExist:
            return Response({"error": "Page not found"}, status=404)

        order = render.order

        with transaction.atomic():
            render.delete()

            # Shift segments
            segments = SectionSegment.objects.filter(issue_section__issue=issue)
            for seg in segments:
                if seg.start_page == order and seg.end_page == order:
                    seg.delete()
                elif seg.start_page <= order <= seg.end_page:
                    seg.end_page -= 1
                    if seg.start_page > seg.end_page:
                        seg.delete()
                    else:
                        seg.save()
                elif seg.start_page > order:
                    seg.start_page -= 1
                    seg.end_page -= 1
                    seg.save()

            # Shift remaining pages in ascending order
            renders_to_shift = issue.renders.filter(order__gt=order).order_by('order')
            for r in renders_to_shift:
                r.order -= 1
                r.save()

        return Response(IssueReaderSerializer(issue, context={'request': request}).data)

class MagazineViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Magazine.objects.all()
    serializer_class = MagazineSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'magazine_slug'

    def get_queryset(self):
        qs = super().get_queryset()
        tag_slug = self.request.query_params.get('tag')
        if tag_slug:
            qs = qs.filter(tags__slug=tag_slug)
        return qs

class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

class SectionViewSet(viewsets.ModelViewSet):
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

from django.db.models.functions import Collate

class PersonViewSet(viewsets.ModelViewSet):
    queryset = Person.objects.all().order_by(Collate('name', 'und-x-icu'))
    serializer_class = PersonSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'aliases', 'disambiguation']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        tag_slug = self.request.query_params.get('tag')
        if tag_slug:
            qs = qs.filter(tags__slug=tag_slug)
        return qs

    def get_serializer_class(self):
        if self.action in ['retrieve', 'update', 'partial_update']:
            return PersonDetailSerializer
        return PersonSerializer

    @action(detail=True, methods=['get'])
    def credits(self, request, pk=None, **kwargs):
        person = self.get_object()
        credits = Credit.objects.filter(person=person).select_related(
            'issue_section__issue__magazine',
            'issue_section__section'
        ).order_by('-issue_section__issue__publishing_date')

        page = self.paginate_queryset(credits)
        if page is not None:
            serializer = PersonCreditSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = PersonCreditSerializer(credits, many=True, context={'request': request})
        return Response(serializer.data)
