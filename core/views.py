import hashlib
import zipfile
from typing import cast

from django.http import HttpResponse, Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiResponse, OpenApiParameter
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Issue, Magazine
from .serializers import IssueDetailSerializer, IssueListSerializer
from .services import get_issue_pages, get_page_image


@extend_schema_view(
    list=extend_schema(
        summary='Listar edições da revista',
        description="Retorna todas as edições de uma revista específica",
    ),
    retrieve=extend_schema(
        summary="Detalhar issue",
        description="Retorna detalhes completos da edição",
    ),
    create=extend_schema(
        summary="Criar issue",
    ),
    update=extend_schema(
        summary="Atualizar issue",
    ),
    partial_update=extend_schema(
        summary="Atualizar parcialmente issue",
    ),
    destroy=extend_schema(
        summary="Remover issue",
    ),
)
class IssueViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        qs = Issue.objects.all()

        magazine = self.kwargs.get('magazine_slug')
        if magazine:
            qs = qs.for_magazine_slug(magazine)

        if self.action == 'list':
            return qs.for_list()

        if self.action == 'retrieve':
            return qs.for_detail()

        if self.action in ['pages', 'page_image']:
            return qs.for_reader()

        return qs

    queryset = get_queryset

    def get_object(self):
        obj = cast(Issue, super().get_object())

        magazine_slug = self.kwargs.get('magazine_slug')

        if magazine_slug and obj.magazine.slug != magazine_slug:
            raise Http404()

        return obj

    def get_serializer_class(self):
        if self.action == 'list':
            return IssueListSerializer
        return IssueDetailSerializer

    def perform_create(self, serializer):
        magazine_slug = self.kwargs.get('magazine_slug')
        if not magazine_slug:
            raise Http404("Magazine slug is required")

        try:
            magazine = Magazine.objects.get(slug=magazine_slug)
        except Magazine.DoesNotExist:
            raise Http404("Magazine not found")

        return serializer.save(magazine=magazine)

    def perform_update(self, serializer):
        magazine_slug = self.kwargs.get('magazine_slug')

        if not magazine_slug:
            return serializer.save()

        if serializer.instance.magazine.slug != magazine_slug:
            raise Http404("Magazine mismatch")

        return serializer.save()

    @extend_schema(
        summary="Listar páginas do CBZ",
        description="Retorna a lista de páginas disponíveis na edição",
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Lista de páginas",
            )
        }
    )
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

    @extend_schema(
        summary="Obter imagem da página",
        description="Retorna a imagem JPEG de uma página específica",
        parameters=[
            OpenApiParameter(
                name='index',
                type=OpenApiTypes.INT,
                location='path',
                description='Índice da página'
            )
        ],
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="Imagem JPEG"
            )
        }
    )
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


class PublicIssueViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Issue.objects.all()
    serializer_class = IssueListSerializer

    @extend_schema(
        summary="Issues recentes",
        description="Retorna as edições mais recentes",
        responses=IssueListSerializer(many=True)
    )
    def list(self, request):
        qs = Issue.objects.order_by('-created_at')[:10]
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
