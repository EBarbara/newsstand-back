from rest_framework import serializers

from .models import Issue, IssueSection, Section, Person, Credit, Magazine, RenderAsset, SectionSegment


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
        ]

class IssueReaderSerializer(serializers.ModelSerializer):
    renders = RenderSerializer(many=True, read_only=True)
    sections = IssueSectionSerializer(source='issue_sections', many=True, read_only=True)

    class Meta:
        model = Issue
        fields = [
            'id',
            'publishing_date',
            'edition',
            'renders',
            'sections',
        ]

class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ['id', 'name', ]

class MagazineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Magazine
        fields = ['name', 'slug']

class IssueListSerializer(serializers.ModelSerializer):
    magazine = MagazineSerializer(read_only=True)
    cover = serializers.SerializerMethodField()

    def get_cover(self, obj):
        first = obj.renders.order_by('order').first()
        return first.image.url if first else None

    class Meta:
        model = Issue
        fields = ['id', 'publishing_date', 'edition', 'magazine', 'cover']

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
