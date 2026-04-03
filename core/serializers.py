from rest_framework import serializers

from .models import Issue, IssueCover, IssueSection, Section, Person, Credit


class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ['name', ]


class IssueCoverSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueCover
        fields = ['id', 'image']


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = '__all__'


class CreditSerializer(serializers.ModelSerializer):
    person = PersonSerializer(read_only=True)
    person_id = serializers.PrimaryKeyRelatedField(
        queryset=Person.objects.all(),
        source='person',
        write_only=True
    )

    class Meta:
        model = Credit
        fields = ['id', 'person', 'person_id', 'role']


class IssueSectionSerializer(serializers.ModelSerializer):
    section = SectionSerializer(read_only=True)
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=IssueSection.objects.all(),
        source='section',
        write_only=True
    )
    credits = CreditSerializer(many=True, read_only=True)
    page_indexes = serializers.SerializerMethodField()

    class Meta:
        model = IssueSection
        fields = ['id', 'section', 'section_id', 'issue', 'page', 'page_indexes', 'credits']

    def get_page_indexes(self, obj):
        return obj.page_indexes_list


class IssueDetailSerializer(serializers.ModelSerializer):
    covers = IssueCoverSerializer(many=True, read_only=True)
    sections = IssueSectionSerializer(many=True, read_only=True)

    class Meta:
        model = Issue
        fields = ['id', 'publishing_date', 'edition', 'file_path', 'covers', 'sections']


class IssueListSerializer(serializers.ModelSerializer):
    covers = IssueCoverSerializer(many=True, read_only=True)

    class Meta:
        model = Issue
        fields = ['id', 'publishing_date', 'edition', 'file_path', 'covers']
