import json
from typing import Optional

from django.db import transaction

from rest_framework import serializers
from rest_framework.request import Request

from .models import Issue, IssueSection, Section, Person, Credit, Magazine, Render, SectionSegment, PersonLink, Tag, \
    PersonRelationship, IssueSectionRelationship, Publisher, MagazinePublisher
from .utils import get_absolute_media_url, get_issue_cover, calculate_age_at_date


class IssueCoverMixin:
    context: dict

    def get_cover(self, obj):
        request: Request | None = self.context.get("request")
        cover = self._get_cover_render(obj)
        if cover is None: return None
        return get_absolute_media_url(cover.image.url, request)

    def _get_cover_render(self, obj) -> Optional[Render]:
        return get_issue_cover(obj)

    def get_cover_focus_x(self, obj):
        cover = self._get_cover_render(obj)
        return cover.focus_x if cover else 0

    def get_cover_focus_y(self, obj):
        cover = self._get_cover_render(obj)
        return cover.focus_y if cover else 50


def get_lowest_level_tags(tags):
    """Filters a list/queryset of Tag objects, keeping only leaf/lowest-level tags in the hierarchy."""
    if not tags:
        return []
    tags_list = list(tags)
    ancestor_ids = set()
    for t in tags_list:
        curr = t.parent
        while curr:
            ancestor_ids.add(curr.id)
            curr = curr.parent
    return [t for t in tags_list if t.id not in ancestor_ids]


class TagSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']


class TagSerializer(serializers.ModelSerializer):
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        source='parent',
        required=False,
        allow_null=True
    )

    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'description', 'image', 'parent_id']

    def to_internal_value(self, data):
        if 'image' in data and (data['image'] == '' or data['image'] == 'null'):
            if hasattr(data, 'copy'):
                data = data.copy()
            data['image'] = None
        return super().to_internal_value(data)


class TagTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'children']

    def get_children(self, obj):
        return TagTreeSerializer(obj.children.all(), many=True).data


class TagDetailSerializer(serializers.ModelSerializer):
    parent = TagSimpleSerializer(read_only=True)
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        source='parent',
        required=False,
        allow_null=True
    )
    children = TagSimpleSerializer(many=True, read_only=True)
    ancestors = serializers.SerializerMethodField()
    descendants_tree = serializers.SerializerMethodField()

    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'description', 'image', 'parent', 'parent_id', 'children', 'ancestors', 'descendants_tree']

    def to_internal_value(self, data):
        if 'image' in data and (data['image'] == '' or data['image'] == 'null'):
            if hasattr(data, 'copy'):
                data = data.copy()
            data['image'] = None
        return super().to_internal_value(data)

    def get_ancestors(self, obj):
        ancestors = []
        curr = obj.parent
        while curr:
            ancestors.insert(0, TagSimpleSerializer(curr).data)
            curr = curr.parent
        return ancestors

    def get_descendants_tree(self, obj):
        return TagTreeSerializer(obj.children.all(), many=True).data

    def validate_parent(self, value):
        if value is None:
            return value
        
        if self.instance and value.id == self.instance.id:
            raise serializers.ValidationError("Uma tag não pode ser mãe de si mesma.")
            
        if self.instance:
            curr = value
            while curr:
                if curr.id == self.instance.id:
                    raise serializers.ValidationError(
                        "Relação circular detectada: a tag pai proposta é um descendente desta tag."
                    )
                curr = curr.parent
                
        return value


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
    country_code = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = ['id', 'name', 'photo', 'photo_focus_x', 'photo_focus_y', 'aliases', 'disambiguation', 'birth_date',
                  'death_date', 'country', 'country_code', 'tags', 'gender', 'gender_display', 'is_group', 'members']

    def get_country_code(self, obj):
        from .utils import resolve_country_code
        return resolve_country_code(obj.country)

    def get_tags(self, obj):
        lowest_tags = get_lowest_level_tags(obj.tags.all())
        return TagSerializer(lowest_tags, many=True, context=self.context).data


class PersonLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonLink
        fields = ['id', 'url', 'label']


class PersonRelationshipSerializer(serializers.ModelSerializer):
    # This is a flat representation for the frontend
    person_id = serializers.IntegerField()
    person_name = serializers.CharField(read_only=True)
    label = serializers.CharField()
    inverse_label = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_from = serializers.BooleanField(read_only=True)

    class Meta:
        model = PersonRelationship
        fields = ['id', 'person_id', 'person_name', 'label', 'inverse_label', 'is_from', 'order']


class PersonDetailSerializer(serializers.ModelSerializer):
    links = PersonLinkSerializer(many=True, required=False)
    # We'll use a SerializerMethodField to get credits with issue info
    credits = serializers.SerializerMethodField()
    relationships = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    country_code = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = [
            'id',
            'name',
            'disambiguation',
            'birth_date',
            'death_date',
            'country',
            'country_code',
            'biography',
            'photo',
            'photo_focus_x',
            'photo_focus_y',
            'aliases',
            'links',
            'credits',
            'relationships',
            'tags',
            'tag_ids',
            'gender',
            'gender_display',
            'is_group',
            'members'
        ]

    def get_country_code(self, obj):
        from .utils import resolve_country_code
        return resolve_country_code(obj.country)

    def get_tags(self, obj):
        lowest_tags = get_lowest_level_tags(obj.tags.all())
        return TagSerializer(lowest_tags, many=True, context=self.context).data

    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        source='tags',
        many=True,
        required=False
    )

    def to_internal_value(self, data):
        # Create a mutable copy of the data if it's a QueryDict
        if hasattr(data, 'copy'):
            data = data.copy()

        # Handle links passed as a JSON string (common in multipart/form-data)
        links = data.get('links')
        if isinstance(links, str):
            try:
                parsed_links = json.loads(links)
                # QueryDict requires setlist to handle lists correctly
                if hasattr(data, 'setlist'):
                    data.setlist('links', parsed_links)
                else:
                    data['links'] = parsed_links
            except (json.JSONDecodeError, TypeError):
                pass

        # Handle relationships passed as a JSON string
        relationships = data.get('relationships')
        if isinstance(relationships, str):
            try:
                parsed_rels = json.loads(relationships)
                if hasattr(data, 'setlist'):
                    data.setlist('relationships', parsed_rels)
                else:
                    data['relationships'] = parsed_rels
            except (json.JSONDecodeError, TypeError):
                pass

        return super().to_internal_value(data)

    def get_credits(self, obj):
        credits_data = Credit.objects.filter(person=obj).select_related(
            'issue_section__issue__magazine',
            'issue_section__section'
        )
        return PersonCreditSerializer(credits_data, many=True, context=self.context).data

    def get_relationships(self, obj):
        rels = []
        # Relationships where obj is from_person
        for r in obj.relationships_from.all().select_related('to_person'):
            rels.append({
                'id': r.id,
                'person_id': r.to_person.id,
                'person_name': r.to_person.name,
                'label': r.label,
                'inverse_label': r.inverse_label,
                'is_from': True,
                'order': r.order
            })
        # Relationships where obj is to_person
        for r in obj.relationships_to.all().select_related('from_person'):
            if r.inverse_label:
                rels.append({
                    'id': r.id,
                    'person_id': r.from_person.id,
                    'person_name': r.from_person.name,
                    'label': r.inverse_label,
                    'inverse_label': r.label,
                    'is_from': False,
                    'order': r.order
                })
        return sorted(rels, key=lambda x: (x['order'], x['id']))

    @transaction.atomic
    def update(self, instance: Person, validated_data: dict) -> Person:
        # Pop links_data from validated_data
        links_data = validated_data.pop('links', None)

        # Fallback: if links_data is None, try to get it from initial_data
        # This covers cases where DRF validation might have skipped or failed the nested field
        if links_data is None and 'links' in self.initial_data:
            links_raw = self.initial_data.get('links')
            if isinstance(links_raw, str):
                try:
                    links_data = json.loads(links_raw)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(links_raw, list):
                links_data = links_raw

        # Pop relationships_data
        relationships_data = validated_data.pop('relationships', None)
        if relationships_data is None and 'relationships' in self.initial_data:
            rels_raw = self.initial_data.get('relationships')
            if isinstance(rels_raw, str):
                try:
                    relationships_data = json.loads(rels_raw)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(rels_raw, list):
                relationships_data = rels_raw

        # Update main instance fields
        # ManyToMany fields need to be handled separately or using .set()
        tags = validated_data.pop('tags', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if tags is not None:
            instance.tags.set(tags)

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

        # Perform relationships update
        if relationships_data is not None:
            # This is tricky because we only want to delete/update records where THIS person is 'from_person'
            # OR where they are 'to_person' but the record belongs to the relationship list.

            # Simple approach for now: delete all relationships where this person is 'from_person'
            # and recreate them. 
            # Note: Relationships where this person is 'to_person' are managed by the other person's profile,
            # BUT the user might want to edit them here.

            # To keep it simple and avoid complex logic, we'll only allow editing relationships
            # where the current person is 'from_person'.

            instance.relationships_from.all().delete()
            for rel in relationships_data:
                if isinstance(rel, dict):
                    to_person_id = rel.get('person_id')
                    label = rel.get('label')
                    inverse_label = rel.get('inverse_label')
                    order = rel.get('order', 0)

                    if to_person_id and label:
                        try:
                            to_person = Person.objects.get(id=to_person_id)
                            PersonRelationship.objects.create(
                                from_person=instance,
                                to_person=to_person,
                                label=label,
                                inverse_label=inverse_label,
                                order=order
                            )
                        except Person.DoesNotExist:
                            pass

        return instance


class PersonCreditSerializer(serializers.ModelSerializer):
    magazine_name = serializers.CharField(source='issue_section.issue.magazine.name', read_only=True)
    magazine_slug = serializers.CharField(source='issue_section.issue.magazine.slug', read_only=True)
    issue_edition = serializers.CharField(source='issue_section.issue.edition', read_only=True)
    issue_volume = serializers.CharField(source='issue_section.issue.volume', read_only=True, allow_null=True)
    issue_id = serializers.IntegerField(source='issue_section.issue.id', read_only=True)
    issue_cover = serializers.SerializerMethodField(method_name='get_cover_image')
    issue_cover_focus_x = serializers.SerializerMethodField()
    issue_cover_focus_y = serializers.SerializerMethodField()
    section_title = serializers.CharField(source='issue_section.title', read_only=True)
    section_translated_title = serializers.CharField(source='issue_section.translated_title', read_only=True, allow_null=True)
    section_type = serializers.CharField(source='issue_section.section.name', read_only=True)
    start_page = serializers.SerializerMethodField()
    render_ids = serializers.PrimaryKeyRelatedField(
        source='renders',
        many=True,
        read_only=True
    )
    issue_date = serializers.DateField(source='issue_section.issue.publishing_date', read_only=True)
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
            'issue_volume',
            'issue_date',
            'issue_id',
            'issue_cover',
            'issue_cover_focus_x',
            'issue_cover_focus_y',
            'section_title',
            'section_translated_title',
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
        return calculate_age_at_date(person.birth_date, issue_date, person.death_date)

    def _get_cover_render(self, obj) -> Optional[Render]:
        return get_issue_cover(obj.issue_section.issue)

    def get_cover_image(self, obj):
        try:
            cover = self._get_cover_render(obj)
            if cover and cover.image:
                request = self.context.get('request')
                return get_absolute_media_url(cover.image.url, request)
        except (AttributeError, ValueError):
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
        return calculate_age_at_date(person.birth_date, issue_date, person.death_date)


class IssueSectionRelationshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueSectionRelationship
        fields = ['id', 'from_issue_section', 'to_issue_section', 'label', 'inverse_label', 'order']


def get_section_relationships(obj: IssueSection) -> list:
    rels = []
    # Relationships where obj is from_issue_section
    for r in obj.relationships_from.all().select_related(
        'to_issue_section__issue__magazine',
        'to_issue_section__section'
    ):
        first_segment = r.to_issue_section.segments.order_by('start_page').first()
        start_page = first_segment.start_page if first_segment else None

        rels.append({
            'id': r.id,
            'issue_section_id': r.to_issue_section.id,
            'issue_section_title': r.to_issue_section.title,
            'issue_section_translated_title': r.to_issue_section.translated_title,
            'section_name': r.to_issue_section.section.name,
            'magazine_name': r.to_issue_section.issue.magazine.name,
            'magazine_slug': r.to_issue_section.issue.magazine.slug,
            'issue_edition': r.to_issue_section.issue.edition,
            'issue_volume': r.to_issue_section.issue.volume,
            'issue_id': r.to_issue_section.issue.id,
            'start_page': start_page,
            'label': r.label,
            'inverse_label': r.inverse_label,
            'is_from': True,
            'order': r.order
        })

    # Relationships where obj is to_issue_section
    for r in obj.relationships_to.all().select_related(
        'from_issue_section__issue__magazine',
        'from_issue_section__section'
    ):
        if r.inverse_label:
            first_segment = r.from_issue_section.segments.order_by('start_page').first()
            start_page = first_segment.start_page if first_segment else None

            rels.append({
                'id': r.id,
                'issue_section_id': r.from_issue_section.id,
                'issue_section_title': r.from_issue_section.title,
                'issue_section_translated_title': r.from_issue_section.translated_title,
                'section_name': r.from_issue_section.section.name,
                'magazine_name': r.from_issue_section.issue.magazine.name,
                'magazine_slug': r.from_issue_section.issue.magazine.slug,
                'issue_edition': r.from_issue_section.issue.edition,
                'issue_volume': r.from_issue_section.issue.volume,
                'issue_id': r.from_issue_section.issue.id,
                'start_page': start_page,
                'label': r.inverse_label,
                'inverse_label': r.label,
                'is_from': False,
                'order': r.order
            })
    return sorted(rels, key=lambda x: (x['order'], x['id']))


class IssueSectionSerializer(serializers.ModelSerializer):
    section = SectionSerializer(read_only=True)
    segments = SectionSegmentSerializer(many=True, read_only=True)
    credits = CreditSerializer(many=True, read_only=True)
    relationships = serializers.SerializerMethodField()

    class Meta:
        model = IssueSection
        fields = [
            'id',
            'section',
            'title',
            'translated_title',
            'text_content',
            'segments',
            'credits',
            'relationships',
            'order',
        ]

    def get_relationships(self, obj):
        return get_section_relationships(obj)


class GlobalIssueSectionSerializer(serializers.ModelSerializer):
    magazine_name = serializers.CharField(source='issue.magazine.name', read_only=True)
    magazine_slug = serializers.CharField(source='issue.magazine.slug', read_only=True)
    issue_edition = serializers.CharField(source='issue.edition', read_only=True)
    issue_volume = serializers.CharField(source='issue.volume', read_only=True, allow_null=True)
    issue_id = serializers.IntegerField(source='issue.id', read_only=True)
    issue_date = serializers.DateField(source='issue.publishing_date', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    section_id = serializers.IntegerField(source='section.id', read_only=True)

    start_page = serializers.SerializerMethodField()
    first_page_image = serializers.SerializerMethodField()
    first_page_type = serializers.SerializerMethodField()
    credits = CreditSerializer(many=True, read_only=True)
    relationships = serializers.SerializerMethodField()

    class Meta:
        model = IssueSection
        fields = [
            'id', 'title', 'translated_title', 'section_name', 'section_id', 'magazine_name', 'magazine_slug',
            'issue_edition', 'issue_volume', 'issue_date', 'issue_id', 'start_page',
            'first_page_image', 'first_page_type', 'credits', 'relationships', 'order'
        ]

    def get_relationships(self, obj):
        return get_section_relationships(obj)

    def get_start_page(self, obj: IssueSection):
        first_segment = obj.segments.order_by('start_page').first()
        return first_segment.start_page if first_segment else None

    def _get_first_render(self, obj: IssueSection) -> Optional[Render]:
        start_page = self.get_start_page(obj)
        if start_page is not None:
            return obj.issue.renders.filter(order=start_page).first()
        return None

    def get_first_page_image(self, obj: IssueSection) -> Optional[str]:
        render = self._get_first_render(obj)
        if render and render.image:
            request = self.context.get('request')
            return get_absolute_media_url(render.image.url, request)
        return None

    def get_first_page_type(self, obj):
        render = self._get_first_render(obj)
        return render.page_type if render else 'NORMAL'


class IssueSectionWriteSerializer(serializers.ModelSerializer):
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        source='section',
    )

    segments = SectionSegmentSerializer(many=True)
    credits = CreditSerializer(many=True, required=False)
    relationships = serializers.JSONField(required=False, write_only=True)

    class Meta:
        model = IssueSection
        fields = ['id', 'section_id', 'title', 'translated_title', 'text_content', 'order', 'segments', 'credits', 'relationships']

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
        segments_data = validated_data.pop('segments', [])
        credits_data = validated_data.pop('credits', [])
        relationships_data = validated_data.pop('relationships', [])

        issue_section = IssueSection.objects.create(**validated_data)

        if segments_data:
            for seg in segments_data:
                SectionSegment.objects.create(issue_section=issue_section, **seg)

        if credits_data:
            for credit in credits_data:
                renders = credit.pop('renders', [])
                c = Credit.objects.create(issue_section=issue_section, **credit)
                c.renders.set(renders)

        if relationships_data:
            for rel in relationships_data:
                if isinstance(rel, dict):
                    to_section_id = rel.get('issue_section_id')
                    label = rel.get('label')
                    inverse_label = rel.get('inverse_label')
                    order = rel.get('order', 0)

                    if to_section_id and label:
                        try:
                            to_section = IssueSection.objects.get(id=to_section_id)
                            IssueSectionRelationship.objects.create(
                                from_issue_section=issue_section,
                                to_issue_section=to_section,
                                label=label,
                                inverse_label=inverse_label,
                                order=order
                            )
                        except IssueSection.DoesNotExist:
                            pass

        return issue_section

    @transaction.atomic
    def update(self, instance: IssueSection, validated_data: dict) -> IssueSection:
        relationships_data = validated_data.pop('relationships', None)

        for attr, value in list(validated_data.items()):
            if attr not in ['segments', 'credits']:
                setattr(instance, attr, value)
        instance.save()

        if 'segments' in validated_data:
            segments_data = validated_data.pop('segments')
            instance.segments.all().delete()
            for seg in segments_data:
                SectionSegment.objects.create(issue_section=instance, **seg)

        if 'credits' in validated_data:
            credits_data = validated_data.pop('credits')
            instance.credits.all().delete()
            for credit in credits_data:
                renders = credit.pop('renders', [])
                c = Credit.objects.create(issue_section=instance, **credit)
                c.renders.set(renders)

        if relationships_data is not None:
            instance.relationships_from.all().delete()
            for rel in relationships_data:
                if isinstance(rel, dict):
                    to_section_id = rel.get('issue_section_id')
                    label = rel.get('label')
                    inverse_label = rel.get('inverse_label')
                    order = rel.get('order', 0)

                    if to_section_id and label:
                        try:
                            to_section = IssueSection.objects.get(id=to_section_id)
                            IssueSectionRelationship.objects.create(
                                from_issue_section=instance,
                                to_issue_section=to_section,
                                label=label,
                                inverse_label=inverse_label,
                                order=order
                            )
                        except IssueSection.DoesNotExist:
                            pass

        return instance

    def to_representation(self, instance):
        return IssueSectionSerializer(instance, context=self.context).data

class PublisherSimpleSerializer(serializers.ModelSerializer):
    country_code = serializers.SerializerMethodField()
    magazines_count = serializers.SerializerMethodField()

    class Meta:
        model = Publisher
        fields = ['id', 'name', 'translated_name', 'country', 'country_code', 'website', 'logo', 'aliases', 'description', 'slug', 'magazines_count']

    def get_country_code(self, obj):
        from .utils import resolve_country_code
        return resolve_country_code(obj.country)

    def get_magazines_count(self, obj):
        return obj.magazine_publishers.count()


class PublisherMagazineSerializer(serializers.ModelSerializer):
    magazine_name = serializers.CharField(source='magazine.name', read_only=True)
    magazine_slug = serializers.CharField(source='magazine.slug', read_only=True)
    magazine_logo = serializers.SerializerMethodField()
    start_date = serializers.DateField(read_only=True)
    end_date = serializers.DateField(read_only=True)

    class Meta:
        model = MagazinePublisher
        fields = ['magazine_name', 'magazine_slug', 'magazine_logo', 'start_date', 'end_date']

    def get_magazine_logo(self, obj):
        try:
            if obj.magazine.logo:
                request = self.context.get('request')
                return get_absolute_media_url(obj.magazine.logo.url, request)
        except Exception:
            pass
        return None


class PublisherDetailSerializer(serializers.ModelSerializer):
    magazines = serializers.SerializerMethodField()
    country_code = serializers.SerializerMethodField()
    logo = serializers.ImageField(required=False, allow_null=True)
    magazines_count = serializers.SerializerMethodField()

    class Meta:
        model = Publisher
        fields = [
            'id', 'name', 'translated_name', 'country', 'country_code', 'website', 
            'logo', 'aliases', 'description', 'slug', 'magazines', 'magazines_count'
        ]

    def get_country_code(self, obj):
        from .utils import resolve_country_code
        return resolve_country_code(obj.country)

    def get_magazines_count(self, obj):
        return obj.magazine_publishers.count()

    def get_magazines(self, obj):
        return PublisherMagazineSerializer(obj.magazine_publishers.all(), many=True, context=self.context).data

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()

        aliases = data.get('aliases')
        if isinstance(aliases, str):
            try:
                parsed_aliases = json.loads(aliases)
                if hasattr(data, 'setlist'):
                    data.setlist('aliases', parsed_aliases)
                else:
                    data['aliases'] = parsed_aliases
            except (json.JSONDecodeError, TypeError):
                pass
        return super().to_internal_value(data)


class MagazinePublisherSerializer(serializers.ModelSerializer):
    publisher = PublisherSimpleSerializer(read_only=True)
    publisher_id = serializers.PrimaryKeyRelatedField(
        queryset=Publisher.objects.all(),
        source='publisher',
        write_only=True
    )

    class Meta:
        model = MagazinePublisher
        fields = ['publisher', 'publisher_id', 'start_date', 'end_date']


class MagazineSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        source='tags',
        many=True,
        required=False
    )
    logo = serializers.ImageField(required=False, allow_null=True)
    issues_count = serializers.SerializerMethodField()
    periodic_issues_count = serializers.SerializerMethodField()
    special_issues_count = serializers.SerializerMethodField()
    country_code = serializers.SerializerMethodField()
    publishers = MagazinePublisherSerializer(source='magazine_publishers', many=True, read_only=True)

    class Meta:
        model = Magazine
        fields = [
            'id', 'name', 'slug', 'publishers', 'language', 'country', 'country_code',
            'volume', 'description', 'tags', 'tag_ids', 'logo', 'issues_count', 
            'periodic_issues_count', 'special_issues_count'
        ]

    def get_country_code(self, obj):
        from .utils import resolve_country_code
        return resolve_country_code(obj.country)

    def get_issues_count(self, obj) -> int:
        return obj.issue_set.count()

    def get_periodic_issues_count(self, obj) -> int:
        return obj.issue_set.filter(is_special=False).count()

    def get_special_issues_count(self, obj) -> int:
        return obj.issue_set.filter(is_special=True).count()

    def get_tags(self, obj):
        lowest_tags = get_lowest_level_tags(obj.tags.all())
        return TagSerializer(lowest_tags, many=True, context=self.context).data

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()

        tag_ids = data.get('tag_ids')
        if isinstance(tag_ids, str):
            try:
                parsed_ids = json.loads(tag_ids)
                if hasattr(data, 'setlist'):
                    data.setlist('tag_ids', parsed_ids)
                else:
                    data['tag_ids'] = parsed_ids
            except (json.JSONDecodeError, TypeError):
                if ',' in tag_ids:
                    parsed_ids = [int(x.strip()) for x in tag_ids.split(',') if x.strip().isdigit()]
                    if hasattr(data, 'setlist'):
                        data.setlist('tag_ids', parsed_ids)
                    else:
                        data['tag_ids'] = parsed_ids
                elif tag_ids.isdigit():
                    parsed_ids = [int(tag_ids)]
                    if hasattr(data, 'setlist'):
                        data.setlist('tag_ids', parsed_ids)
                    else:
                        data['tag_ids'] = parsed_ids

        publishers = data.get('publishers')
        if isinstance(publishers, str):
            try:
                parsed_publishers = json.loads(publishers)
                if hasattr(data, 'setlist'):
                    data.setlist('publishers', parsed_publishers)
                else:
                    data['publishers'] = parsed_publishers
            except (json.JSONDecodeError, TypeError):
                pass

        return super().to_internal_value(data)

    @transaction.atomic
    def update(self, instance, validated_data):
        tags = validated_data.pop('tags', None)
        
        publishers_raw = self.initial_data.get('publishers')
        if isinstance(publishers_raw, str):
            try:
                publishers_data = json.loads(publishers_raw)
            except Exception:
                publishers_data = None
        elif isinstance(publishers_raw, list):
            publishers_data = publishers_raw
        else:
            publishers_data = None
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if tags is not None:
            instance.tags.set(tags)
            
        if publishers_data is not None:
            instance.magazine_publishers.all().delete()
            for pub_item in publishers_data:
                pub_id = pub_item.get('publisher_id')
                if pub_id:
                    try:
                        publisher = Publisher.objects.get(id=pub_id)
                        start_date = pub_item.get('start_date') or None
                        end_date = pub_item.get('end_date') or None
                        MagazinePublisher.objects.create(
                            magazine=instance,
                            publisher=publisher,
                            start_date=start_date,
                            end_date=end_date
                        )
                    except Publisher.DoesNotExist:
                        pass
            
        return instance

    @transaction.atomic
    def create(self, validated_data):
        tags = validated_data.pop('tags', None)
        
        publishers_raw = self.initial_data.get('publishers')
        if isinstance(publishers_raw, str):
            try:
                publishers_data = json.loads(publishers_raw)
            except Exception:
                publishers_data = None
        elif isinstance(publishers_raw, list):
            publishers_data = publishers_raw
        else:
            publishers_data = None

        instance = Magazine.objects.create(**validated_data)
        
        if tags is not None:
            instance.tags.set(tags)
            
        if publishers_data is not None:
            for pub_item in publishers_data:
                pub_id = pub_item.get('publisher_id')
                if pub_id:
                    try:
                        publisher = Publisher.objects.get(id=pub_id)
                        start_date = pub_item.get('start_date') or None
                        end_date = pub_item.get('end_date') or None
                        MagazinePublisher.objects.create(
                            magazine=instance,
                            publisher=publisher,
                            start_date=start_date,
                            end_date=end_date
                        )
                    except Publisher.DoesNotExist:
                        pass
            
        return instance


class IssueListSerializer(IssueCoverMixin, serializers.ModelSerializer):
    magazine = MagazineSerializer(read_only=True)
    cover = serializers.SerializerMethodField()
    cover_focus_x = serializers.SerializerMethodField()
    cover_focus_y = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = ['id', 'publishing_date', 'edition', 'volume', 'magazine', 'cover', 'cover_focus_x', 'cover_focus_y',
                  'has_physical_copy', 'is_digital_complete', 'is_special', 'tags']

    def get_tags(self, obj):
        lowest_tags = get_lowest_level_tags(obj.tags.all())
        return TagSerializer(lowest_tags, many=True, context=self.context).data


class IssueReaderSerializer(IssueCoverMixin, serializers.ModelSerializer):
    magazine = MagazineSerializer(read_only=True)
    renders = RenderSerializer(many=True, read_only=True)
    sections = IssueSectionSerializer(source='issue_sections', many=True, read_only=True)
    cover = serializers.SerializerMethodField()
    cover_focus_x = serializers.SerializerMethodField()
    cover_focus_y = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        source='tags',
        many=True,
        required=False
    )

    class Meta:
        model = Issue
        fields = [
            'id',
            'publishing_date',
            'edition',
            'volume',
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
            'tag_ids',
        ]

    def get_tags(self, obj):
        lowest_tags = get_lowest_level_tags(obj.tags.all())
        return TagSerializer(lowest_tags, many=True, context=self.context).data
