from django.contrib.postgres.search import TrigramSimilarity, TrigramStrictWordSimilarity
from django.db import connection
from django.db.models import Case, ExpressionWrapper, FloatField, IntegerField, Min, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce, Least, Round

from ..models import AlternativeTitle, Novel, NovelFromSource


def normalize_query(query):
    """Fold the query the way search_norm() folds titles (SQL side, so both match)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT immutable_unaccent(UPPER(%s))", [query])
        return cursor.fetchone()[0]


def _like(text):
    """LIKE pattern matching ``text`` literally: escapes the backslash, % and _ like Django does."""
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def _run_ids(branches):
    sql = ' UNION '.join(select for select, _ in branches)
    with connection.cursor() as cursor:
        cursor.execute(sql, [value for _, value in branches])
        return [row[0] for row in cursor.fetchall()]


def matching_novel_ids(nq, query):
    """Return ``(title_ids, synopsis_ids)``: novels whose title (main, source, alternative) matches,
    and novels whose synopsis matches. Two queries, so the caller can rank title hits separately
    (the view's Case limits the rank work to them).

    One SELECT per (table, operator): OR-ing the operators on one column makes Postgres drop
    the trigram index for a seq scan. Run once, so the count and page queries don't redo it.
    """
    novel_table = Novel._meta.db_table
    source_table = NovelFromSource._meta.db_table
    alt_table = AlternativeTitle._meta.db_table
    link_table = NovelFromSource.alternative_titles.through._meta.db_table
    # Substring (LIKE), whole-title typo (%), in-title typo (%>). Only LIKE takes the escaped pattern.
    operators = (('LIKE %s', _like(nq)), ('%% %s', nq), ('%%> %s', nq))
    title_selects = (
        f'SELECT id FROM {novel_table} WHERE search_title',
        f'SELECT novel_id FROM {source_table} WHERE search_title',
        f'SELECT s.novel_id FROM {alt_table} a'
        f' JOIN {link_table} m ON m.alternativetitle_id = a.id'
        f' JOIN {source_table} s ON s.id = m.novelfromsource_id WHERE a.search_name',
    )
    title_branches = [(f'{select} {op}', value) for select in title_selects for op, value in operators]
    synopsis_branches = [(f'SELECT novel_id FROM {source_table} WHERE UPPER(synopsis) LIKE %s', _like(query.upper()))]
    return _run_ids(title_branches), _run_ids(synopsis_branches)


def _title_rank(col, nq):
    """Lower is better: match tier * 10 minus the title closeness rounded to 0.1."""
    tier = Case(
        When(**{col: nq}, then=Value(0)),
        When(**{f'{col}__startswith': nq}, then=Value(1)),
        When(**{f'{col}__contains': nq}, then=Value(2)),
        When(Q(**{f'{col}__trigram_similar': nq}) | Q(**{f'{col}__trigram_word_similar': nq}), then=Value(3)),
        default=Value(4),
        output_field=IntegerField(),
    )
    score = TrigramSimilarity(col, nq) + TrigramStrictWordSimilarity(nq, col)
    return ExpressionWrapper(tier * 10 - Round(score, 1), output_field=FloatField())


def title_rank(nq):
    """Best (lowest) rank over the outer novel's main, source and alternative titles; 40 = no title match."""
    source_best = (
        NovelFromSource.objects.filter(novel=OuterRef('pk'))
        .values('novel')
        .annotate(m=Min(_title_rank('search_title', nq)))
        .values('m')[:1]
    )
    alt_best = (
        AlternativeTitle.objects.filter(novels__novel=OuterRef('pk'))
        .order_by()  # drop Meta.ordering ('name'), it would break the GROUP BY
        .annotate(_g=Value(1))
        .values('_g')
        .annotate(m=Min(_title_rank('search_name', nq)))
        .values('m')[:1]
    )
    return Least(
        _title_rank('search_title', nq),
        Coalesce(Subquery(source_best, output_field=FloatField()), 40.0),
        Coalesce(Subquery(alt_best, output_field=FloatField()), 40.0),
        output_field=FloatField(),
    )
