from django.contrib import admin
from .models import Magazine, Issue, RenderAsset, Page, Section, IssueSection, SectionSegment, Person, PersonLink, Credit, Tag

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

@admin.register(Magazine)
class MagazineAdmin(admin.ModelAdmin):
    list_display = ('name', 'publisher', 'country')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('tags',)

@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('magazine', 'publishing_date', 'edition')
    list_filter = ('magazine', 'publishing_date', 'tags')
    filter_horizontal = ('tags',)

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'birth_date')
    search_fields = ('name', 'aliases')
    filter_horizontal = ('tags',)

admin.site.register(Section)
admin.site.register(IssueSection)
admin.site.register(Credit)
admin.site.register(PersonLink)
admin.site.register(RenderAsset)
