from rest_framework import serializers

from .models import Issue, IssueCover, IssueSection, Section, Person, Credit, Magazine


class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ['id', 'name', ]

class MagazineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Magazine
        fields = ['name', 'slug']

class IssueCoverSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueCover
        fields = ['id', 'image', ]

class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'name', ]

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
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        source='section',
        write_only=True
    )
    credits = CreditSerializer(many=True, read_only=True)
    page_indexes = serializers.ListField(child=serializers.IntegerField())
    first_page_index = serializers.SerializerMethodField()

    class Meta:
        model = IssueSection
        fields = ['id', 'section', 'section_id', 'issue', 'page', 'page_indexes', 'credits', 'first_page_index', ]

    def get_first_page_index(self, obj):
        indexes = obj.page_indexes_list
        return min(indexes) if indexes else None

class IssueBaseSerializer(serializers.ModelSerializer):
    covers = IssueCoverSerializer(many=True, read_only=True)
    magazine = MagazineSerializer(read_only=True)
    is_digital = serializers.SerializerMethodField()
    magazine_id = serializers.PrimaryKeyRelatedField(
        queryset=Magazine.objects.all(),
        source='magazine',
        write_only=True
    )

    def get_is_digital(self, obj):
        return bool(obj.file_path)

class IssueDetailSerializer(IssueBaseSerializer):
    sections = IssueSectionSerializer(many=True, read_only=True)

    class Meta:
        model = Issue
        fields = ['id', 'publishing_date', 'edition', 'is_digital', 'file_path', 'magazine', 'magazine_id', 'covers', 'sections', ]

class IssueListSerializer(IssueBaseSerializer):
    class Meta:
        model = Issue
        fields = ['id', 'publishing_date', 'edition', 'is_digital', 'magazine', 'magazine_id', 'covers', ]

class PageSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    name = serializers.CharField()