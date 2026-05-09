from typing import Optional

from django.db import transaction

from rest_framework import serializers
from rest_framework.request import Request

from .models import Issue, IssueSection, Section, Person, Credit, Magazine, Render, SectionSegment, PersonLink, Tag

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']

class IssueCoverMixin:
    context: dict

    def get_cover(self, obj):
        request: Request | None = self.context.get("request")
        cover = self._get_cover_render(obj)
        if cover is None: return None
        url = cover.image.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url

    def _get_cover_render(self, obj) -> Optional[Render]:
        # Prioritize renders marked as covers
        cover = obj.renders.filter(is_cover=True).first()
        # Fallback to the first render by order
        if not cover:
            cover = obj.renders.first()
        return cover

    def get_cover_focus_x(self, obj):
        cover = self._get_cover_render(obj)
        return cover.focus_x if cover else 0

    def get_cover_focus_y(self, obj):
        cover = self._get_cover_render(obj)
        return cover.focus_y if cover else 50

class RenderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Render
        fields = ['id', 'order', 'image', 'is_cover', 'page_type', 'focus_x', 'focus_y', 'width', 'height']

class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'name']

class SectionSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SectionSegment
        fields = ['start_page', 'end_page']

class PersonSerializer(serializers.ModelSerializer):
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    class Meta:
        model = Person
        fields = ['id', 'name', 'photo', 'photo_focus_x', 'photo_focus_y', 'aliases', 'disambiguation', 'birth_date', 'death_date', 'country', 'tags', 'gender', 'gender_display']

class PersonLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonLink
        fields = ['id', 'url', 'label']

class PersonDetailSerializer(serializers.ModelSerializer):
    links = PersonLinkSerializer(many=True, required=False)
    # We'll use a SerializerMethodField to get credits with issue info
    credits = serializers.SerializerMethodField()
    tags = TagSerializer(many=True, read_only=True)
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)

    class Meta:
        model = Person
        fields = [
            'id', 
            'name', 
            'disambiguation',
            'birth_date', 
            'death_date',
            'country', 
            'biography', 
            'photo', 
            'photo_focus_x',
            'photo_focus_y',
            'aliases',
            'links', 
            'credits',
            'tags',
            'gender',
            'gender_display'
        ]

    def to_internal_value(self, data):
        # Create a mutable copy of the data if it's a QueryDict
        if hasattr(data, 'copy'):
            data = data.copy()

        # Handle links passed as a JSON string (common in multipart/form-data)
        links = data.get('links')
        if isinstance(links, str):
            try:
                import json
                parsed_links = json.loads(links)
                # QueryDict requires setlist to handle lists correctly
                if hasattr(data, 'setlist'):
                    data.setlist('links', parsed_links)
                else:
                    data['links'] = parsed_links
            except (json.JSONDecodeError, TypeError):
                pass
        
        return super().to_internal_value(data)

    def get_credits(self, obj):
        credits = Credit.objects.filter(person=obj).select_related(
            'issue_section__issue__magazine',
            'issue_section__section'
        )
        return PersonCreditSerializer(credits, many=True, context=self.context).data

    @transaction.atomic
    def update(self, instance, validated_data):
        # Pop links_data from validated_data
        links_data = validated_data.pop('links', None)
        
        # Fallback: if links_data is None, try to get it from initial_data
        # This covers cases where DRF validation might have skipped or failed the nested field
        if links_data is None and 'links' in self.initial_data:
            links_raw = self.initial_data.get('links')
            if isinstance(links_raw, str):
                try:
                    import json
                    links_data = json.loads(links_raw)
                except:
                    pass
            elif isinstance(links_raw, list):
                links_data = links_raw

        # Update main instance fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Perform links update if data was provided
        if links_data is not None:
            instance.links.all().delete()
            for link in links_data:
                if isinstance(link, dict):
                    # Clean the dict to only include valid fields for PersonLink
                    # and remove ID to avoid conflicts
                    url = link.get('url')
                    label = link.get('label')
                    if url and label:
                        PersonLink.objects.create(
                            person=instance, 
                            url=url, 
                            label=label
                        )
                
        return instance

class PersonCreditSerializer(serializers.ModelSerializer):
    magazine_name = serializers.CharField(source='issue_section.issue.magazine.name', read_only=True)
    magazine_slug = serializers.CharField(source='issue_section.issue.magazine.slug', read_only=True)
    issue_edition = serializers.CharField(source='issue_section.issue.edition', read_only=True)
    issue_id = serializers.IntegerField(source='issue_section.issue.id', read_only=True)
    issue_cover = serializers.SerializerMethodField(method_name='get_cover_image')
    issue_cover_focus_x = serializers.SerializerMethodField()
    issue_cover_focus_y = serializers.SerializerMethodField()
    section_title = serializers.CharField(source='issue_section.title', read_only=True)
    section_type = serializers.CharField(source='issue_section.section.name', read_only=True)
    start_page = serializers.SerializerMethodField()
    render_ids = serializers.PrimaryKeyRelatedField(
        source='renders',
        many=True,
        read_only=True
    )
    age_at_issue = serializers.SerializerMethodField()

    class Meta:
        model = Credit
        fields = [
            'id', 
            'role', 
            'importance',
            'magazine_name', 
            'magazine_slug', 
            'issue_edition', 
            'issue_id', 
            'issue_cover',
            'issue_cover_focus_x',
            'issue_cover_focus_y',
            'section_title', 
            'section_type',
            'start_page',
            'render_ids',
            'age_at_issue'
        ]

    def get_start_page(self, obj):
        # If the credit is anchored to specific pages, return the order of the first one
        first_render = obj.renders.order_by('order').first()
        if first_render:
            return first_render.order
            
        # Fallback to the first segment of the section
        first_segment = obj.issue_section.segments.order_by('start_page').first()
        return first_segment.start_page if first_segment else None

    def get_age_at_issue(self, obj):
        person = obj.person
        issue_date = obj.issue_section.issue.publishing_date
        
        if not issue_date:
            return None

        # Check if posthumous
        if person.death_date and person.death_date <= issue_date:
            return "póstumo"
            
        if not person.birth_date:
            return None
            
        age = issue_date.year - person.birth_date.year - (
            (issue_date.month, issue_date.day) < (person.birth_date.month, person.birth_date.day)
        )
        return f"({age} anos)"

    def _get_cover_render(self, obj) -> Optional[Render]:
        issue = obj.issue_section.issue
        # Prioritize renders marked as covers
        cover = issue.renders.filter(is_cover=True).first()
        # Fallback to order 0
        if not cover:
            cover = issue.renders.filter(order=0).first()
        # Ultimate fallback to any render
        if not cover:
            cover = issue.renders.all().first()
        return cover

    def get_cover_image(self, obj):
        try:
            cover = self._get_cover_render(obj)
            if cover and cover.image:
                return cover.image.url
        except Exception:
            pass
        return None

    def get_issue_cover_focus_x(self, obj):
        cover = self._get_cover_render(obj)
        return cover.focus_x if cover else 0

    def get_issue_cover_focus_y(self, obj):
        cover = self._get_cover_render(obj)
        return cover.focus_y if cover else 50

class CreditSerializer(serializers.ModelSerializer):
    person = PersonSerializer(read_only=True)
    person_id = serializers.PrimaryKeyRelatedField(
        queryset=Person.objects.all(),
        source='person'
    )
    render_ids = serializers.PrimaryKeyRelatedField(
        queryset=Render.objects.all(),
        source='renders',
        many=True,
        required=False
    )
    age_at_issue = serializers.SerializerMethodField()

    class Meta:
        model = Credit
        fields = ['id', 'person', 'person_id', 'role', 'importance', 'render_ids', 'age_at_issue']

    def get_age_at_issue(self, obj):
        person = obj.person
        issue_date = obj.issue_section.issue.publishing_date
        
        if not person.birth_date or not issue_date:
            return None
            
        age = issue_date.year - person.birth_date.year - (
            (issue_date.month, issue_date.day) < (person.birth_date.month, person.birth_date.day)
        )
        return f"({age} anos)"

class IssueSectionSerializer(serializers.ModelSerializer):
    section = SectionSerializer(read_only=True)
    segments = SectionSegmentSerializer(many=True, read_only=True)
    credits = CreditSerializer(many=True, read_only=True)

    class Meta:
        model = IssueSection
        fields = [
            'id',
            'section',
            'title',
            'text_content',
            'segments',
            'credits',
            'order',
        ]

class IssueSectionWriteSerializer(serializers.ModelSerializer):
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        source='section',
    )

    segments = SectionSegmentSerializer(many=True)
    credits = CreditSerializer(many=True, required=False)

    class Meta:
        model = IssueSection
        fields = ['id', 'section_id', 'title', 'text_content', 'order', 'segments', 'credits']

    def validate_segments(self, value):
        for seg in value:
            if seg['start_page'] > seg['end_page']:
                raise serializers.ValidationError(
                    "start_page cannot be greater than end_page"
                )
        return value

    def validate_credits(self, value):
        for credit in value:
            if 'person' not in credit:
                raise serializers.ValidationError(
                    "Cada crédito deve ter uma pessoa selecionada."
                )
        return value

    @transaction.atomic
    def create(self, validated_data: dict) -> IssueSection:
        segments_data = validated_data.pop('segments', None)
        credits_data = validated_data.pop('credits', None)
        
        issue_section = IssueSection.objects.create(**validated_data)

        if segments_data:
            for seg in segments_data:
                SectionSegment.objects.create(issue_section=issue_section, **seg)
            
        if credits_data:
            for credit in credits_data:
                renders = credit.pop('renders', [])
                c = Credit.objects.create(issue_section=issue_section, **credit)
                c.renders.set(renders)

        return issue_section

    @transaction.atomic
    def update(self, instance: IssueSection, validated_data: dict) -> IssueSection:
        segments_data = validated_data.pop('segments', None)
        credits_data = validated_data.pop('credits', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if segments_data is not None:
            instance.segments.all().delete()
            for seg in segments_data:
                SectionSegment.objects.create(issue_section=instance, **seg)
                
        if credits_data is not None:
            instance.credits.all().delete()
            for credit in credits_data:
                renders = credit.pop('renders', [])
                c = Credit.objects.create(issue_section=instance, **credit)
                c.renders.set(renders)

        return instance

    def to_representation(self, instance):
        return IssueSectionSerializer(instance, context=self.context).data

class MagazineSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    class Meta:
        model = Magazine
        fields = ['name', 'slug', 'tags']

class IssueListSerializer(IssueCoverMixin, serializers.ModelSerializer):
    magazine = MagazineSerializer(read_only=True)
    cover = serializers.SerializerMethodField()
    cover_focus_x = serializers.SerializerMethodField()
    cover_focus_y = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = ['id', 'publishing_date', 'edition', 'magazine', 'cover', 'cover_focus_x', 'cover_focus_y', 'has_physical_copy', 'is_digital_complete', 'is_special', 'tags']

class IssueReaderSerializer(IssueCoverMixin, serializers.ModelSerializer):
    magazine = MagazineSerializer(read_only=True)
    renders = RenderSerializer(many=True, read_only=True)
    sections = IssueSectionSerializer(source='issue_sections', many=True, read_only=True)
    cover = serializers.SerializerMethodField()
    cover_focus_x = serializers.SerializerMethodField()
    cover_focus_y = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = [
            'id',
            'publishing_date',
            'edition',
            'magazine',
            'cover',
            'cover_focus_x',
            'cover_focus_y',
            'renders',
            'sections',
            'has_physical_copy',
            'is_digital_complete',
            'is_special',
            'tags',
        ]
