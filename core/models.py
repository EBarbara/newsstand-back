from pathlib import Path

from django.db import models

from .manager import IssueQuerySet


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

class Person(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name='Name')

    class Meta:
        verbose_name = 'Person'
        verbose_name_plural = 'People'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Section(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name='Name')

    class Meta:
        verbose_name = 'Section'
        verbose_name_plural = 'Sections'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Issue(models.Model):
    objects = IssueQuerySet.as_manager()

    magazine = models.ForeignKey(Magazine, on_delete=models.CASCADE, related_name='issues')
    publishing_date = models.DateField(verbose_name='Publishing Date')
    edition = models.IntegerField(null=True, blank=True, verbose_name='Edition')
    file_path = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name='File Path',
        help_text='Absolute path to the .cbz file on your computer/network.',
    )

    class Meta:
        verbose_name = 'Issue'
        verbose_name_plural = 'Issues'
        ordering = ['-publishing_date', '-edition']
        constraints = [
            models.UniqueConstraint(fields=['publishing_date', 'edition'], name='unique_issue_per_date_edition'),
            models.UniqueConstraint(fields=['magazine', 'edition'], name='unique_issue_per_magazine_edition'),
        ]

    def get_path(self) -> Path | None:
        return Path(self.file_path) if self.file_path else None

    def __str__(self) -> str:
        edition_str = f' Ed. {self.edition} ' if self.edition else ''
        return f"{self.publishing_date.strftime('%b/%y')}{edition_str}"


class IssueCover(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='covers', verbose_name='Issue')
    image = models.ImageField(upload_to='covers/', verbose_name='Image')

    class Meta:
        verbose_name = 'Issue Cover'
        verbose_name_plural = 'Issue Covers'

    def __str__(self) -> str:
        return f'Cover for {self.issue}'


class IssueSection(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, verbose_name='Issue', related_name='sections')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, verbose_name='Section')
    page = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Page',
        help_text='The physical page number where this section starts in the issue.',
    )
    page_indexes = models.JSONField(
        verbose_name='Page Indexes',
        help_text='Comma-separated list of image indexes in the CBZ file.',
        default=list,
        blank=True
    )

    @property
    def page_indexes_list(self) -> list[int]:
        return self.page_indexes or []

    class Meta:
        verbose_name = 'Issue Section'
        verbose_name_plural = 'Issue Sections'
        ordering = ['issue', 'page', 'section__name']
        constraints = [models.UniqueConstraint(fields=['issue', 'section'], name='unique_section_per_issue')]

    def __str__(self) -> str:
        page_info = f', p. {self.page}' if self.page else ''
        return f'{self.section} in {self.issue}{page_info}'


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
        ordering = ['issue_section__issue__publishing_date', 'issue_section__page', 'role', 'person__name']

    def __str__(self) -> str:
        role_text = f' as {self.role}' if self.role else ''
        return f"{self.person}{role_text} in {self.issue_section}"
