from django.db import models


class IssueQuerySet(models.QuerySet):
    def with_details(self):
        return self.select_related('magazine').prefetch_related(
            'covers',
            'sections__section',
            'sections__credits__person'
        )

    def ordered(self):
        return self.order_by('-publishing_date', '-edition')

    def for_list(self):
        return self.prefetch_related('covers').only('id', 'publishing_date', 'edition').ordered()

    def for_detail(self):
        return self.with_details().ordered()

    def for_reader(self):
        return self.only('id', 'file_path')

    def for_magazine_slug(self, slug):
        return self.filter(magazine__slug=slug)