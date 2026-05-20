from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta
from rest_framework.request import Request

from .models import Render, Issue


def get_issue_cover(issue: Optional[Issue]) -> Optional[Render]:
    """
    Recupera a renderização de capa de um Issue utilizando uma estratégia unificada de fallback:
    1. Prioriza renderizações explicitamente marcadas como capa.
    2. Fallback para a renderização de ordem 0.
    3. Fallback para a primeira renderização disponível na ordem.
    """

    if not issue:
        return None

    cover = issue.renders.filter(is_cover=True).first()

    if not cover:
        cover = issue.renders.filter(order=0).first()

    if not cover:
        cover = issue.renders.first()

    return cover

def calculate_age_at_date(birth_date: Optional[date], event_date: Optional[date], death_date: Optional[date] = None) -> Optional[str]:
    """
    Calcula a idade de uma pessoa em uma data específica.
    Trata casos de evento póstumo caso a data de óbito seja fornecida.
    """
    if not event_date or not birth_date:
        return None

    if death_date and death_date <= event_date:
        return "póstumo"

    age = relativedelta(event_date, birth_date).years
    return f'({age} anos)'

def get_absolute_media_url(url: Optional[str], request: Optional[Request]) -> Optional[str]:
    """
    Retorna a URL absoluta de uma mídia caso o objeto da requisição esteja presente.
    Caso contrário, retorna a URL relativa.
    """
    if not url:
        return None
    if request is not None:
        return request.build_absolute_uri(url)
    return url