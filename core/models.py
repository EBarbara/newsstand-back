from django.core.exceptions import ValidationError
from django.db import models


# Create your models here.
class Tag(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

class Magazine(models.Model):
    name = models.CharField(max_length=255)
    publisher = models.CharField(max_length=255, null=True, blank=True)
    language = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    slug = models.SlugField(unique=True, db_index=True)
    description = models.TextField(null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='magazines')

    def __str__(self):
        return self.name


class Issue(models.Model):
    magazine = models.ForeignKey(Magazine, on_delete=models.CASCADE)
    publishing_date = models.DateField()
    edition = models.CharField(max_length=255, null=True, blank=True)

    source_file = models.CharField(max_length=1000, null=True, blank=True)
    has_physical_copy = models.BooleanField(default=False, verbose_name='Has Physical Copy')
    is_digital_complete = models.BooleanField(default=False, verbose_name='Is Digital Complete')
    is_special = models.BooleanField(default=False, verbose_name='Is Special Edition')
    tags = models.ManyToManyField(Tag, blank=True, related_name='issues')

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
    focus_x = models.IntegerField(default=0) # % from left
    focus_y = models.IntegerField(default=50) # % from top
    width = models.IntegerField()
    height = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['issue', 'order'], name='unique_render_order_per_issue')
        ]


class Page(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='pages')

    number = models.IntegerField()

    render = models.ForeignKey(Render, on_delete=models.SET_NULL, null=True)

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


class Credit(models.Model):
    IMPORTANCE_CHOICES = [
        (1, 'Major'),      # Protagonist / Star
        (2, 'Regular'),    # Contributor (Photographer, Writer)
        (3, 'Minor'),      # Mention / Click / Paparazzi
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
        ordering = ['importance', 'issue_section__issue__publishing_date', 'issue_section__id', 'role', 'person__name' ]

    def __str__(self) -> str:
        role_text = f' as {self.role}' if self.role else ''
        importance_text = f' [{self.get_importance_display()}]'
        return f"{self.person}{role_text}{importance_text} in {self.issue_section}"
