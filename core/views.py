from PIL import Image
from decouple import config
from django.db import transaction
from django.db.models import Case, When, Q, Value, IntegerField, ExpressionWrapper
from django.db.models.functions import ExtractYear, ExtractMonth, ExtractDay, Collate
from django.http import Http404
from django_filters import rest_framework as django_filters
from django_filters.rest_framework import FilterSet, CharFilter, DateFilter, ChoiceFilter, NumberFilter, BooleanFilter
from rest_framework import status
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from .models import Issue, Magazine, IssueSection, SectionSegment, Render, Tag, Section, Person, Credit
from .pagination import StandardResultsSetPagination
from .serializers import IssueListSerializer, IssueReaderSerializer, MagazineSerializer, TagSerializer, TagDetailSerializer, \
    SectionSerializer, IssueSectionSerializer, IssueSectionWriteSerializer, PersonSerializer, PersonDetailSerializer, \
    PersonCreditSerializer, GlobalIssueSectionSerializer
from .services import process_cbz_file


def get_recent_count():
    return config('ISSUES_RECENT_COUNT', default=10, cast=int)

class IssueFilter(FilterSet):
    tag = CharFilter(method='filter_tags_and')
    tag_direct = CharFilter(method='filter_tags_direct')
    tag_exclude = CharFilter(method='filter_tags_exclude_and')
    year = NumberFilter(field_name='publishing_date', lookup_expr='year')
    year_gt = NumberFilter(field_name='publishing_date', lookup_expr='year__gt')
    year_gte = NumberFilter(field_name='publishing_date', lookup_expr='year__gte')
    year_lt = NumberFilter(field_name='publishing_date', lookup_expr='year__lt')
    year_lte = NumberFilter(field_name='publishing_date', lookup_expr='year__lte')
    year_ne = NumberFilter(field_name='publishing_date', lookup_expr='year', exclude=True)
    is_special = BooleanFilter(field_name='is_special')
    has_physical_copy = BooleanFilter(field_name='has_physical_copy')
    is_digital_complete = BooleanFilter(field_name='is_digital_complete')
    person_tag = CharFilter(method='filter_person_tags_and')
    person_age_gt = NumberFilter(method='filter_person_age')
    person_age_gte = NumberFilter(method='filter_person_age')
    person_age_lt = NumberFilter(method='filter_person_age')
    person_age_lte = NumberFilter(method='filter_person_age')
    person_age_eq = NumberFilter(method='filter_person_age')
    person_age_ne = NumberFilter(method='filter_person_age')

    class Meta:
        model = Issue
        fields = ['is_special', 'has_physical_copy', 'is_digital_complete']

    def filter_tags_and(self, queryset, name, value):
        if not self.request:
            return queryset
        tags = self.request.GET.getlist('tag')
        for t in tags:
            try:
                tag_obj = Tag.objects.get(slug=t)
                descendant_slugs = tag_obj.get_descendant_slugs()
                queryset = queryset.filter(tags__slug__in=descendant_slugs)
            except Tag.DoesNotExist:
                queryset = queryset.none()
        return queryset.distinct()

    def filter_tags_direct(self, queryset, name, value):
        if not self.request:
            return queryset
        tags = self.request.GET.getlist('tag_direct')
        for t in tags:
            queryset = queryset.filter(tags__slug=t)
        return queryset.distinct()

    def filter_tags_exclude_and(self, queryset, name, value):
        if not self.request:
            return queryset
        tags = self.request.GET.getlist('tag_exclude')
        for t in tags:
            try:
                tag_obj = Tag.objects.get(slug=t)
                descendant_slugs = tag_obj.get_descendant_slugs()
                queryset = queryset.exclude(tags__slug__in=descendant_slugs)
            except Tag.DoesNotExist:
                pass
        return queryset.distinct()

    def filter_person_tags_and(self, queryset, name, value):
        if not self.request:
            return queryset
        person_tags = self.request.GET.getlist('person_tag')
        for pt in person_tags:
            queryset = queryset.filter(
                issue_sections__credits__person__tags__slug=pt,
                issue_sections__credits__importance=1
            )
        return queryset.distinct()

    def filter_person_age(self, queryset, name, value):
        op_map = {
            'person_age_gt': 'gt',
            'person_age_gte': 'gte',
            'person_age_lt': 'lt',
            'person_age_lte': 'lte',
            'person_age_eq': 'exact',
            'person_age_ne': 'ne'
        }
        op = op_map.get(name, 'exact')
        
        # Age calculation logic: Year diff minus 1 if birthday hasn't occurred yet in the publication year
        age_expr = (
            ExtractYear('publishing_date') - ExtractYear('issue_sections__credits__person__birth_date') - 
            Case(
                When(
                    Q(publishing_date__month__lt=ExtractMonth('issue_sections__credits__person__birth_date')) |
                    Q(publishing_date__month=ExtractMonth('issue_sections__credits__person__birth_date'),
                      publishing_date__day__lt=ExtractDay('issue_sections__credits__person__birth_date')),
                    then=Value(1)
                ),
                default=Value(0),
                output_field=IntegerField()
            )
        )
        
        filter_kwargs = {f'_p_age_at_pub__{op}': value}
        return queryset.filter(
            issue_sections__credits__person__birth_date__isnull=False
        ).annotate(
            _p_age_at_pub=ExpressionWrapper(age_expr, output_field=IntegerField())
        ).filter(**filter_kwargs).distinct()

class IssueViewSet(viewsets.ModelViewSet):
    queryset = Issue.objects.all()
    filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = IssueFilter

    def get_queryset(self):
        qs = super().get_queryset()

        qs = qs.select_related('magazine')
        if self.action in ['list', 'recent']:
            qs = qs.prefetch_related('renders', 'tags')

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

        if magazine_slug and isinstance(lookup_value, str):
            try:
                candidates = queryset.filter(
                    magazine__slug=magazine_slug,
                    edition__iexact=lookup_value
                )
                
                volume = self.request.query_params.get('volume')
                if volume:
                    candidates = candidates.filter(volume=volume)
                
                if candidates.count() == 1:
                    obj = candidates.first()
                    self.check_object_permissions(self.request, obj)
                    return obj
                elif candidates.count() > 1:
                    if lookup_value.isdigit():
                        try:
                            obj = queryset.get(pk=lookup_value)
                            self.check_object_permissions(self.request, obj)
                            return obj
                        except Issue.DoesNotExist:
                            pass
                    obj = candidates.first()
                    self.check_object_permissions(self.request, obj)
                    return obj
                else:
                    raise Issue.DoesNotExist
            except Issue.DoesNotExist:
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
        volume = request.data.get('volume')

        try:
            issue, count = process_cbz_file(
                file_obj=file_obj,
                filename=file_obj.name,
                magazine_slug=magazine_slug,
                edition=edition,
                publishing_date=publishing_date,
                volume=volume
            )
            
            if 'has_physical_copy' in request.data:
                issue.has_physical_copy = request.data.get('has_physical_copy') in ['true', 'True', True]
            if 'is_digital_complete' in request.data:
                issue.is_digital_complete = request.data.get('is_digital_complete') in ['true', 'True', True]
            if 'is_special' in request.data:
                issue.is_special = request.data.get('is_special') in ['true', 'True', True]
            issue.save()

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Failed to process CBZ: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = self.get_serializer(issue)
        return Response({
            **serializer.data,
            'pages_count': count
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser], url_path='import_cbz')
    def import_cbz_to_issue(self, request, *args, **kwargs):
        issue = self.get_object()
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"error": "No file provided. Field must be named 'file'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            issue, count = process_cbz_file(
                file_obj=file_obj,
                filename=file_obj.name,
                issue=issue,
                append=True
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Failed to process CBZ: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = self.get_serializer(issue)
        return Response({
            **serializer.data,
            'pages_count': count
        })

    @action(detail=False, methods=['post'], parser_classes=[JSONParser])
    def create_empty(self, request, *args, **kwargs):
        magazine_slug = request.data.get('magazine')
        edition = request.data.get('edition')
        publishing_date = request.data.get('date')
        volume = request.data.get('volume')
        
        has_physical_copy = request.data.get('has_physical_copy', False)
        is_digital_complete = request.data.get('is_digital_complete', False)
        is_special = request.data.get('is_special', False)

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
                volume=volume,
                publishing_date=publishing_date,
                has_physical_copy=has_physical_copy,
                is_digital_complete=is_digital_complete,
                is_special=is_special
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
                "id": issue_section.pk,
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
            
            render = Render.objects.create(
                issue=issue,
                order=order,
                width=width,
                height=height,
                image=file
            )

        return Response(IssueReaderSerializer(issue, context={'request': request}).data)

    @action(detail=True, methods=['patch'], url_path='update-page/(?P<render_pk>[^/.]+)')
    def update_page(self, request, render_pk=None, *args, **kwargs):
        issue = self.get_object()
        try:
            render = issue.renders.get(pk=render_pk)
        except Render.DoesNotExist:
            return Response({"error": "Render not found"}, status=404)

        from .serializers import RenderSerializer
        serializer = RenderSerializer(render, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['post'], url_path='reorder-pages')
    def reorder_pages(self, request, *args, **kwargs):
        issue = self.get_object()
        render_ids = request.data.get('render_ids', [])

        if not render_ids:
            return Response({"error": "No render_ids provided"}, status=400)

        with transaction.atomic():
            # First pass: set to temporary negative values to avoid collisions
            for i, r_id in enumerate(render_ids):
                Render.objects.filter(id=r_id, issue=issue).update(order=-(i + 1))
            
            # Second pass: set to final positive values (1-based indexing)
            for i, r_id in enumerate(render_ids):
                Render.objects.filter(id=r_id, issue=issue).update(order=i + 1)

        return Response(IssueReaderSerializer(issue, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='replace-page/(?P<render_pk>[^/.]+)')
    def replace_page(self, request, render_pk=None, *args, **kwargs):
        issue = self.get_object()
        file = request.FILES.get('file')
        
        try:
            render = issue.renders.get(pk=render_pk)
        except Render.DoesNotExist:
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
        except Render.DoesNotExist:
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

class MagazineViewSet(viewsets.ModelViewSet):
    queryset = Magazine.objects.all()
    serializer_class = MagazineSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'magazine_slug'
    filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name', 'publisher', 'description']

    def get_queryset(self):
        qs = super().get_queryset()
        tag_slug = self.request.query_params.get('tag')
        if tag_slug:
            qs = qs.filter(tags__slug=tag_slug)
        return qs

class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    lookup_field = 'slug'
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'slug']

    def get_serializer_class(self):
        if self.action in ['retrieve', 'update', 'partial_update']:
            return TagDetailSerializer
        return TagSerializer

class SectionViewSet(viewsets.ModelViewSet):
    queryset = Section.objects.all().order_by('name')
    serializer_class = SectionSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

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

class PersonFilter(FilterSet):
    name = CharFilter(lookup_expr='icontains')
    name_exclude = CharFilter(field_name='name', lookup_expr='icontains', exclude=True)
    birth_date_after = DateFilter(field_name='birth_date', lookup_expr='gte')
    birth_date_before = DateFilter(field_name='birth_date', lookup_expr='lte')
    tag = CharFilter(method='filter_tag')
    tag_direct = CharFilter(method='filter_tag_direct')
    tag_exclude = CharFilter(method='filter_tag_exclude')
    gender = ChoiceFilter(choices=Person.GENDER_CHOICES)
    gender_exclude = ChoiceFilter(field_name='gender', choices=Person.GENDER_CHOICES, exclude=True)
    country_exclude = CharFilter(field_name='country', lookup_expr='exact', exclude=True)
    
    class Meta:
        model = Person
        fields = ['gender', 'country']

    def filter_tag(self, queryset, name, value):
        try:
            tag_obj = Tag.objects.get(slug=value)
            descendant_slugs = tag_obj.get_descendant_slugs()
            return queryset.filter(tags__slug__in=descendant_slugs).distinct()
        except Tag.DoesNotExist:
            return queryset.none()

    def filter_tag_direct(self, queryset, name, value):
        return queryset.filter(tags__slug=value).distinct()

    def filter_tag_exclude(self, queryset, name, value):
        try:
            tag_obj = Tag.objects.get(slug=value)
            descendant_slugs = tag_obj.get_descendant_slugs()
            return queryset.exclude(tags__slug__in=descendant_slugs).distinct()
        except Tag.DoesNotExist:
            return queryset

class PersonViewSet(viewsets.ModelViewSet):
    queryset = Person.objects.all().order_by(Collate('name', 'und-x-icu'))
    serializer_class = PersonSerializer
    filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PersonFilter
    search_fields = ['name', 'aliases', 'disambiguation']
    ordering_fields = ['name', 'created_at', 'birth_date', 'country']

    def get_serializer_class(self):
        if self.action in ['retrieve', 'update', 'partial_update']:
            return PersonDetailSerializer
        return PersonSerializer

    @action(detail=True, methods=['get'])
    def credits(self, request, pk=None, **kwargs):
        person = self.get_object()
        credits_data = Credit.objects.filter(person=person).select_related(
            'issue_section__issue__magazine',
            'issue_section__section'
        ).order_by('-issue_section__issue__publishing_date')

        page = self.paginate_queryset(credits_data)
        if page is not None:
            serializer = PersonCreditSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = PersonCreditSerializer(credits_data, many=True, context={'request': request})
        return Response(serializer.data)

class IssueSectionFilter(FilterSet):
    section = NumberFilter(field_name='section_id')
    issue = NumberFilter(field_name='issue_id')
    magazine = CharFilter(field_name='issue__magazine__slug')
    year = NumberFilter(field_name='issue__publishing_date', lookup_expr='year')

    class Meta:
        model = IssueSection
        fields = ['section', 'issue', 'magazine', 'year']

class GlobalIssueSectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IssueSection.objects.all().select_related(
        'issue__magazine', 
        'section'
    ).prefetch_related(
        'segments', 
        'credits__person'
    ).order_by('-issue__publishing_date', 'order', 'id')
    
    serializer_class = GlobalIssueSectionSerializer
    filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = IssueSectionFilter
    search_fields = ['title', 'text_content', 'section__name', 'issue__magazine__name']
    ordering_fields = ['issue__publishing_date', 'order']
    pagination_class = StandardResultsSetPagination
