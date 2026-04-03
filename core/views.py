import hashlib
import os.path
import zipfile

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Issue
from .serializers import IssueDetailSerializer, IssueListSerializer
from .utils import is_safe_path, get_cbz_file_list


class IssueViewSet(viewsets.ModelViewSet):
    queryset = Issue.objects.prefetch_related(
        'covers',
        'sections__section',
        'sections__credits__person',
    ).order_by('-publishing_date', '-edition')

    def get_serializer_class(self):
        if self.action == 'list':
            return IssueListSerializer
        return IssueDetailSerializer

    @action(detail=True, methods=['get'])
    def pages(self, request, pk=None):
        issue = self.get_object()

        if not issue.file_path:
            return Response({'error': 'No file'}, status=404)
        if not is_safe_path(issue.file_path):
            return Response({'error': 'Invalid path'}, status=403)
        if not os.path.exists(issue.file_path):
            return Response({'error': 'File not found'}, status=404)

        try:
            files = get_cbz_file_list(issue)
        except zipfile.BadZipFile:
            return Response({'error': 'Invalid CBZ file'}, status=500)
        except (FileNotFoundError, PermissionError):
            return Response({'error': 'File access error'}, status=500)

        return Response([{'index': i, 'name': name} for i, name in enumerate(files)])

    @action(detail=True, methods=['get'], url_path='pages/(?P<index>[^/.]+)')
    def page_image(self, request, pk=None, index=None):
        issue = self.get_object()

        if not issue.file_path:
            return HttpResponse(status=404)
        if not is_safe_path(issue.file_path):
            return HttpResponse(status=403)
        if not os.path.exists(issue.file_path):
            return HttpResponse(status=404)

        try:
            index = int(index)
        except ValueError:
            return HttpResponse(status=400)

        try:
            files = get_cbz_file_list(issue)

            if index < 0 or index >= len(files):
                return HttpResponse(status=404)

            with zipfile.ZipFile(issue.file_path) as zf:
                data = zf.read(files[index])
        except zipfile.BadZipFile:
            return HttpResponse(status=500)
        except (FileNotFoundError, PermissionError):
            return HttpResponse(status=500)

        response = HttpResponse(data, content_type='image/jpeg')
        response['Cache-Control'] = 'public, max-age=86400'  # 1 dia
        etag = hashlib.md5(data).hexdigest()
        response['ETag'] = etag
        return response
