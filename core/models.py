from django.core.exceptions import ValidationError
from django.db import models


# Create your models here.

class Magazine(models.Model):
    name = models.CharField(max_length=255)
    publisher = models.CharField(max_length=255, null=True, blank=True)
    language = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    slug = models.SlugField(unique=True, db_index=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name


class Issue(models.Model):
    magazine = models.ForeignKey(Magazine, on_delete=models.CASCADE)
    publishing_date = models.DateField()
    edition = models.CharField(max_length=255, null=True, blank=True)

    source_file = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        verbose_name = 'Issue'
        verbose_name_plural = 'Issues'
        ordering = ['-publishing_date', '-edition']
        constraints = [
            models.UniqueConstraint(fields=['publishing_date', 'edition'], name='unique_issue_per_date_edition'),
            models.UniqueConstraint(fields=['magazine', 'edition'], name='unique_issue_per_magazine_edition'),
        ]

    def __str__(self) -> str:
        edition_str = f' Ed. {self.edition} ' if self.edition else ''
        return f"{self.publishing_date.strftime('%b/%y')}{edition_str}"


class RenderAsset(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='renders')

    order = models.IntegerField()  # navegação

    image = models.ImageField(upload_to='pages/')

    width = models.IntegerField()
    height = models.IntegerField()

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['issue', 'order'], name='unique_render_order_per_issue')
        ]


class Page(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='pages')

    number = models.IntegerField()

    render = models.ForeignKey(RenderAsset, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['number']
        constraints = [
            models.UniqueConstraint(fields=['issue', 'number'], name='unique_page_number_per_issue')
        ]


class Section(models.Model):
    name = models.CharField(max_length=255, unique = True)

    class Meta:
        verbose_name = 'Section'
        verbose_name_plural = 'Sections'

    def __str__(self) -> str:
        return self.name


class IssueSection(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, verbose_name='Issue', related_name='issue_sections')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, verbose_name='Section')
    title = models.CharField(max_length=255, null=True, blank=True)
    order = models.IntegerField()
    text_content = models.TextField(
        null=True,
        blank=True,
        help_text="Optional textual content of the section."
    )


class SectionSegment(models.Model):
    issue_section = models.ForeignKey(IssueSection, related_name='segments', on_delete=models.CASCADE)

    start_page = models.IntegerField()
    end_page = models.IntegerField()



class Person(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name='Name')

    class Meta:
        verbose_name = 'Person'
        verbose_name_plural = 'People'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Credit(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, verbose_name='Person')
    issue_section = models.ForeignKey(
        IssueSection,
        on_delete=models.CASCADE,
        verbose_name='IssueSection',
        related_name='credits'
    )
    role = models.CharField(max_length=255, null=True, blank=True, verbose_name='Role')

    class Meta:
        verbose_name = 'Credit'
        verbose_name_plural = 'Credits'
        ordering = ['issue_section__issue__publishing_date', 'issue_section__id', 'role', 'person__name' ]

    def __str__(self) -> str:
        role_text = f' as {self.role}' if self.role else ''
        return f"{self.person}{role_text} in {self.issue_section}"
