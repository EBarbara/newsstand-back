import hashlib
import zipfile

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Issue
from .serializers import IssueDetailSerializer, IssueListSerializer
from .services import get_issue_pages, get_page_image


class IssueViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        qs = Issue.objects.all()

        if self.action == 'list':
            return qs.for_list()

        if self.action == 'retrieve':
            return qs.for_detail()

        if self.action in ['pages', 'page_image']:
            return qs.for_reader()

        return qs

    queryset = get_queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return IssueListSerializer
        return IssueDetailSerializer

    @action(detail=True, methods=['get'])
    def pages(self, request, pk=None):
        issue = self.get_object()

        try:
            files = get_issue_pages(issue)
        except FileNotFoundError:
            return Response({'error': 'File not found'}, status=404)
        except PermissionError:
            return Response({'error': 'Invalid path'}, status=403)
        except zipfile.BadZipFile:
            return Response({'error': 'Invalid CBZ file'}, status=500)

        return Response([{'index': i, 'name': name} for i, name in enumerate(files)])

    @action(detail=True, methods=['get'], url_path='pages/(?P<index>[^/.]+)')
    def page_image(self, request, pk=None, index=None):
        issue = self.get_object()

        try:
            index = int(index)
        except ValueError:
            return HttpResponse(status=400)

        try:
            data = get_page_image(issue, index)
        except FileNotFoundError:
            return HttpResponse(status=404)
        except PermissionError:
            return HttpResponse(status=403)
        except IndexError:
            return HttpResponse(status=404)
        except ValueError:
            return HttpResponse(status=500)

        response = HttpResponse(data, content_type='image/jpeg')
        response['Cache-Control'] = 'public, max-age=86400'  # 1 dia
        response['ETag'] = hashlib.md5(data).hexdigest()

        return response
