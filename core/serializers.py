from typing import Optional

from django.db import transaction

from rest_framework import serializers
from rest_framework.request import Request

from .models import Issue, IssueSection, Section, Person, Credit, Magazine, RenderAsset, SectionSegment, PersonLink

class IssueCoverMixin:
    context: dict

    def get_cover(self, obj):
        request: Request | None = self.context.get("request")

        first: Optional[RenderAsset] = obj.renders.first()

        if first is None:
            return None

        url = first.image.url

        if request is not None:
            return request.build_absolute_uri(url)

        return url

class RenderSerializer(serializers.ModelSerializer):
    class Meta:
        model = RenderAsset
        fields = ['id', 'order', 'image']

class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'name']

class SectionSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SectionSegment
        fields = ['start_page', 'end_page']

class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ['id', 'name', 'photo', 'photo_focus_x', 'photo_focus_y']

class PersonLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonLink
        fields = ['id', 'url', 'label']

class PersonDetailSerializer(serializers.ModelSerializer):
    links = PersonLinkSerializer(many=True, required=False)
    # We'll use a SerializerMethodField to get credits with issue info
    credits = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = [
            'id', 
            'name', 
            'birth_date', 
            'country', 
            'biography', 
            'photo', 
            'photo_focus_x',
            'photo_focus_y',
            'links', 
            'credits'
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
    issue_cover = serializers.ImageField(source='issue_section.issue.cover', read_only=True)
    section_title = serializers.CharField(source='issue_section.title', read_only=True)
    section_type = serializers.CharField(source='issue_section.section.name', read_only=True)

    class Meta:
        model = Credit
        fields = [
            'id', 
            'role', 
            'magazine_name', 
            'magazine_slug', 
            'issue_edition', 
            'issue_id', 
            'issue_cover',
            'section_title', 
            'section_type'
        ]

class CreditSerializer(serializers.ModelSerializer):
    person = PersonSerializer(read_only=True)
    person_id = serializers.PrimaryKeyRelatedField(
        queryset=Person.objects.all(),
        source='person',
        write_only=True
    )

    class Meta:
        model = Credit
        fields = ['id', 'person', 'person_id', 'role', ]

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
                Credit.objects.create(issue_section=issue_section, **credit)

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
                Credit.objects.create(issue_section=instance, **credit)

        return instance

    def to_representation(self, instance):
        return IssueSectionSerializer(instance, context=self.context).data

class MagazineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Magazine
        fields = ['name', 'slug']

class IssueListSerializer(IssueCoverMixin, serializers.ModelSerializer):
    magazine = MagazineSerializer(read_only=True)
    cover = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = ['id', 'publishing_date', 'edition', 'magazine', 'cover']

class IssueReaderSerializer(IssueCoverMixin, serializers.ModelSerializer):
    magazine = MagazineSerializer(read_only=True)
    renders = RenderSerializer(many=True, read_only=True)
    sections = IssueSectionSerializer(source='issue_sections', many=True, read_only=True)
    cover = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = [
            'id',
            'publishing_date',
            'edition',
            'magazine',
            'cover',
            'renders',
            'sections',
        ]
