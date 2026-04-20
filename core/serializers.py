from typing import TYPE_CHECKING, Optional

from rest_framework import serializers
from rest_framework.request import Request

from .models import Issue, IssueSection, Section, Person, Credit, Magazine, RenderAsset, SectionSegment

if TYPE_CHECKING:
    from rest_framework.serializers import Serializer

class IssueCoverMixin:
    context: dict

    def get_cover(self, obj):
        request: Request | None = self.context.get("request")

        renders = list(obj.renders.all())
        first: Optional[RenderAsset] = renders[0] if renders else None

        if first is None:
            return None

        url = first.image.url

        if request is not None:
            return request.build_absolute_uri(url)

        return url

class RenderSerializer(serializers.ModelSerializer):
    class Meta:
        model = RenderAsset
        fields = ['order', 'image']

class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'name']

class SectionSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SectionSegment
        fields = ['start_page', 'end_page']

class IssueSectionSerializer(serializers.ModelSerializer):
    section = SectionSerializer(read_only=True)
    segments = SectionSegmentSerializer(many=True, read_only=True)

    class Meta:
        model = IssueSection
        fields = [
            'id',
            'section',
            'segments',
            'text_content',
            'order',
        ]

class IssueSectionWriteSerializer(serializers.ModelSerializer):
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        source='section',
    )

    segments = SectionSegmentSerializer(many=True)

    class Meta:
        model = IssueSection
        fields = ['id', 'section_id', 'text_content', 'order', 'segments']

    def create(self, validated_data: dict) -> IssueSection:
        segments_data = validated_data.pop('segments', [])
        issue_section = IssueSection.objects.create(**validated_data)

        for seg in segments_data:
            SectionSegment.objects.create(issue_section=issue_section, **seg)

        return issue_section

class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ['id', 'name', ]

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
