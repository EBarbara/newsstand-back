import os
from typing import TYPE_CHECKING

from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import slugify

if TYPE_CHECKING:
    from django.db.models import Manager

# Create your models here.
class Tag(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='tags/', null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_descendant_ids(self):
        ids = [self.id]
        for child in self.children.all():
            ids.extend(child.get_descendant_ids())
        return ids

    def get_descendant_slugs(self):
        slugs = [self.slug]
        for child in self.children.all():
            slugs.extend(child.get_descendant_slugs())
        return slugs

    class Meta:
        ordering = ['name']


class Publisher(models.Model):
    name = models.CharField(max_length=255)
    translated_name = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    website = models.URLField(null=True, blank=True)
    logo = models.ImageField(upload_to='publishers/', null=True, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    slug = models.SlugField(unique=True, db_index=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Magazine(models.Model):
    name = models.CharField(max_length=255)
    language = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    slug = models.SlugField(unique=True, db_index=True)
    volume = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='magazines')
    logo = models.ImageField(upload_to='logos/', null=True, blank=True)
    publishers = models.ManyToManyField(Publisher, through='MagazinePublisher', blank=True, related_name='magazines')

    class Meta:
        ordering = ['volume', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'volume'],
                name='unique_magazine_name_volume',
                nulls_distinct=False
            )
        ]


    def save(self, *args, **kwargs):
        if self.volume:
            self.volume = self.volume.strip()
            if not self.volume:
                self.volume = None
        else:
            self.volume = None

        base_slug = slugify(self.name)
        expected_slug = f"{base_slug}-{slugify(self.volume)}" if self.volume else base_slug
        
        if not self.slug:
            self.slug = expected_slug
        elif self.pk:
            try:
                orig = Magazine.objects.get(pk=self.pk)
                if orig.name != self.name or orig.volume != self.volume:
                    self.slug = expected_slug
            except Magazine.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        volume_str = f' (Vol. {self.volume})' if self.volume else ''
        return f"{self.name}{volume_str}"


class MagazinePublisher(models.Model):
    magazine = models.ForeignKey(Magazine, on_delete=models.CASCADE, related_name='magazine_publishers')
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name='magazine_publishers')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['start_date', 'publisher__name']
        constraints = [
            models.UniqueConstraint(
                fields=['magazine', 'publisher'],
                name='unique_magazine_publisher'
            )
        ]


class Issue(models.Model):
    magazine = models.ForeignKey(Magazine, on_delete=models.CASCADE)
    publishing_date = models.DateField()
    edition = models.CharField(max_length=255, null=True, blank=True)
    volume = models.CharField(max_length=255, null=True, blank=True)

    has_physical_copy = models.BooleanField(default=False, verbose_name='Has Physical Copy')
    is_digital_complete = models.BooleanField(default=False, verbose_name='Is Digital Complete')
    is_special = models.BooleanField(default=False, verbose_name='Is Special Edition')
    tags = models.ManyToManyField(Tag, blank=True, related_name='issues')

    if TYPE_CHECKING:
        renders: Manager[Render]
        issue_sections: Manager[IssueSection]

    class Meta:
        verbose_name = 'Issue'
        verbose_name_plural = 'Issues'
        ordering = ['-publishing_date', '-edition']
        constraints = [
            models.UniqueConstraint(
                fields=['magazine', 'volume', 'edition'],
                name='unique_issue_per_magazine_volume_edition',
                nulls_distinct=False
            ),
        ]

    def __str__(self) -> str:
        volume_str = f' Vol. {self.volume}' if self.volume else ''
        edition_str = f' Ed. {self.edition}' if self.edition else ''
        parts = [self.publishing_date.strftime('%b/%y')]
        if volume_str:
            parts.append(volume_str.strip())
        if edition_str:
            parts.append(edition_str.strip())
        return " - ".join(parts)


class Render(models.Model):
    PAGE_TYPES = [
        ('NORMAL', 'Normal'),
        ('SPREAD', 'Página Dupla'),
        ('GATEFOLD', 'Desdobrável'),
    ]

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='renders')
    image = models.ImageField(upload_to='renders/')
    order = models.IntegerField()
    is_cover = models.BooleanField(default=False)
    page_type = models.CharField(max_length=10, choices=PAGE_TYPES, default='NORMAL')
    focus_x = models.IntegerField(default=0)  # % from left
    focus_y = models.IntegerField(default=50)  # % from top
    width = models.IntegerField()
    height = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['issue', 'order'], name='unique_render_order_per_issue')
        ]


class Section(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name = 'Section'
        verbose_name_plural = 'Sections'

    def __str__(self) -> str:
        return self.name


class IssueSection(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, verbose_name='Issue', related_name='issue_sections')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, verbose_name='Section')
    title = models.CharField(max_length=255, null=True, blank=True)
    translated_title = models.CharField(max_length=255, null=True, blank=True)
    order = models.IntegerField()
    text_content = models.TextField(
        null=True,
        blank=True,
        help_text="Optional textual content of the section."
    )

    if TYPE_CHECKING:
        segments: Manager['SectionSegment']
        credits: Manager['Credit']
        relationships_from: Manager['IssueSectionRelationship']
        relationships_to: Manager['IssueSectionRelationship']


class SectionSegment(models.Model):
    issue_section = models.ForeignKey(IssueSection, related_name='segments', on_delete=models.CASCADE)

    start_page = models.IntegerField()
    end_page = models.IntegerField()


class IssueSectionRelationship(models.Model):
    from_issue_section = models.ForeignKey(IssueSection, on_delete=models.CASCADE, related_name='relationships_from')
    to_issue_section = models.ForeignKey(IssueSection, on_delete=models.CASCADE, related_name='relationships_to')
    label = models.CharField(max_length=100, verbose_name='Label (From -> To)')
    inverse_label = models.CharField(max_length=100, null=True, blank=True, verbose_name='Inverse Label (To -> From)')
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'IssueSection Relationship'
        verbose_name_plural = 'IssueSection Relationships'
        constraints = [
            models.UniqueConstraint(
                fields=['from_issue_section', 'to_issue_section'],
                name='unique_issuesection_relationship'
            )
        ]

    def __str__(self) -> str:
        return f"{self.from_issue_section} -> {self.label} -> {self.to_issue_section}"



class Person(models.Model):
    name = models.CharField(max_length=255, verbose_name='Name')
    disambiguation = models.CharField(max_length=255, null=True, blank=True, verbose_name='Disambiguation')
    birth_date = models.DateField(null=True, blank=True, verbose_name='Birth Date')
    death_date = models.DateField(null=True, blank=True, verbose_name='Death Date')
    country = models.CharField(max_length=255, null=True, blank=True, verbose_name='Country')
    biography = models.TextField(null=True, blank=True, verbose_name='Biography')
    photo = models.ImageField(upload_to='people/', null=True, blank=True, verbose_name='Photo')
    photo_focus_x = models.IntegerField(default=50, verbose_name='Photo Focus X (%)')
    photo_focus_y = models.IntegerField(default=50, verbose_name='Photo Focus Y (%)')
    aliases = models.JSONField(default=list, blank=True, verbose_name='Aliases')
    is_group = models.BooleanField(default=False, verbose_name='Is Group')
    members = models.JSONField(default=list, blank=True, verbose_name='Members')
    tags = models.ManyToManyField(Tag, blank=True, related_name='people')

    GENDER_CHOICES = [
        (None, 'Não informado'),
        ('M', 'Masculino'),
        ('F', 'Feminino'),
        ('TM', 'Transsexual Masculino'),
        ('TF', 'Transsexual Feminino'),
        ('I', 'Intersexual'),
        ('NB', 'Não-binário'),
    ]
    gender = models.CharField(
        max_length=2,
        choices=GENDER_CHOICES,
        null=True,
        blank=True,
        verbose_name='Gênero'
    )

    if TYPE_CHECKING:
        links: Manager['PersonLink']
        relationships_from: Manager['PersonRelationship']

    class Meta:
        verbose_name = 'Person'
        verbose_name_plural = 'People'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'disambiguation'],
                name='unique_person_name_disambiguation',
                nulls_distinct=False
            )
        ]

    def __str__(self) -> str:
        return self.name


class PersonLink(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='links')
    url = models.URLField()
    label = models.CharField(max_length=255)

    def __str__(self) -> str:
        return f"{self.label} ({self.person.name})"


class PersonRelationship(models.Model):
    from_person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='relationships_from')
    to_person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='relationships_to')
    label = models.CharField(max_length=100, verbose_name='Label (From -> To)')
    inverse_label = models.CharField(max_length=100, null=True, blank=True, verbose_name='Inverse Label (To -> From)')
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Person Relationship'
        verbose_name_plural = 'Person Relationships'

    def __str__(self) -> str:
        return f"{self.from_person.name} -> {self.label} -> {self.to_person.name}"


class Credit(models.Model):
    IMPORTANCE_CHOICES = [
        (1, 'Major'),  # Protagonist / Star
        (2, 'Regular'),  # Contributor (Photographer, Writer)
        (3, 'Minor'),  # Mention / Click / Paparazzi
    ]

    person = models.ForeignKey(Person, on_delete=models.CASCADE, verbose_name='Person')
    issue_section = models.ForeignKey(
        IssueSection,
        on_delete=models.CASCADE,
        verbose_name='IssueSection',
        related_name='credits'
    )
    role = models.CharField(max_length=255, null=True, blank=True, verbose_name='Role')
    importance = models.IntegerField(choices=IMPORTANCE_CHOICES, default=2, verbose_name='Importance')
    renders = models.ManyToManyField(
        Render,
        blank=True,
        related_name='credits',
        verbose_name='Specific Pages'
    )

    class Meta:
        verbose_name = 'Credit'
        verbose_name_plural = 'Credits'
        ordering = ['importance', 'issue_section__issue__publishing_date', 'issue_section__id', 'role', 'person__name']

    if TYPE_CHECKING:
        def get_importance_display(self) -> str: ...            

    def __str__(self) -> str:
        role_text = f' as {self.role}' if self.role else ''
        importance_text = f' [{self.get_importance_display()}]'
        return f"{self.person}{role_text}{importance_text} in {self.issue_section}"


class CountryMapping(models.Model):
    name = models.CharField(max_length=255, unique=True, help_text="Common name or alias of the country (e.g. 'brasil', 'coreia do sul', 'kr')")
    code = models.CharField(max_length=2, help_text="2-letter ISO 3166-1 country code (e.g. 'br', 'kr', 'bf')")

    def save(self, *args, **kwargs):
        self.name = self.name.lower().strip()
        self.code = self.code.lower().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} -> {self.code.upper()}"

    class Meta:
        verbose_name = 'Country Mapping'
        verbose_name_plural = 'Country Mappings'
        ordering = ['name']


@receiver(post_delete, sender=Render)
@receiver(post_delete, sender=Person)
@receiver(post_delete, sender=Magazine)
@receiver(post_delete, sender=Tag)
@receiver(post_delete, sender=Publisher)
def delete_files_on_delete(sender, instance, **kwargs):
    """Deletes uploaded files from filesystem when the model instance is deleted."""
    for field in instance._meta.fields:
        if isinstance(field, models.FileField):
            file_field = getattr(instance, field.name)
            if file_field and file_field.name:
                try:
                    if os.path.isfile(file_field.path):
                        os.remove(file_field.path)
                except (OSError, ValueError):
                    pass
