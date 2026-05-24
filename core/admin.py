from django.contrib import admin

from .models import Magazine, Issue, Render, Section, IssueSection, Person, PersonLink, Credit, Tag, CountryMapping


@admin.register(CountryMapping)
class CountryMappingAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


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
    list_display = ('magazine', 'publishing_date', 'edition', 'is_special')
    list_filter = ('magazine', 'publishing_date', 'is_special', 'tags')
    filter_horizontal = ('tags',)

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'gender', 'country', 'birth_date', 'death_date')
    search_fields = ('name', 'aliases')
    list_filter = ('gender', 'country', 'tags')
    filter_horizontal = ('tags',)

admin.site.register(Section)
admin.site.register(IssueSection)
admin.site.register(Credit)
admin.site.register(PersonLink)
admin.site.register(Render)
