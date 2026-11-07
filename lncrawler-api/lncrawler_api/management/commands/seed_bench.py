"""Build a large, deterministic benchmark database for performance work.

Point it at a separate database (POSTGRES_DB=lncrawler_bench). Anything whose
name lacks 'bench' is refused unless --yes-i-know is given. Bulk rows are
generated server-side with INSERT ... SELECT over generate_series; values come
from hashes of row keys, so the same --scale and --seed give the same
distributions (UUID keys are random, so which exact row gets a vote may differ).
Chapter bodies are not stored in the DB: they are written as JSON files under
<LNCRAWL_OUTPUT_PATH>/_bench/shared-source/json.
"""

import json
import os
import random
import re
import time

import psycopg
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from psycopg import sql

from lncrawler_api.models import (
    AlternativeTitle,
    Audiobook,
    Author,
    AuthorAlias,
    Editor,
    Tag,
    TagAlias,
    Translator,
)
from lncrawler_api.services.chapter_stats import refresh_chapter_stats
from lncrawler_api.services.novel_rankings import refresh_novel_rankings
from lncrawler_api.utils.author_names import normalize_author
from lncrawler_api.utils.tag_utils import normalize_tag

SOURCE_PATH = '_bench/shared-source'
FILE_COUNT = 12000
EXTERNAL_COUNT = 60
FORCED_SOURCES = 5

VOCAB = """
blade dragon kingdom shadow crown sword mage tower forest river storm ember
oath realm throne rogue knight relic prophecy sorcerer dungeon ruin hollow
moon sun ash iron silver gold crystal serpent wyvern phoenix golem spirit
ghost king queen prince princess witch hunter assassin guardian sentinel
citadel fortress harbor isle sea mountain valley desert glacier marsh forge
scroll grimoire rune sigil chalice amulet curse blessing pact betrayal
exile rebellion empire republic legion banner emblem journey quest pilgrim
wanderer stranger omen herald vow vengeance redemption legacy ascension
descent trial labyrinth vault catacomb abyss heaven hell lantern candle
winter summer autumn spring dawn dusk midnight twilight eclipse comet star
flame frost thunder lightning tempest whisper echo silence secret hidden
lost forgotten ancient sacred cursed fallen broken rising eternal iron-clad
warden keeper seeker oracle saint demon angel titan giant elf dwarf orc
beast monster summoner necromancer alchemist artificer engineer merchant
caravan tavern inn village city capital borderland frontier wilds ruins
sanctum temple shrine bridge gate wall road path gale tide bloom thorn raven
wolf hawk lion bear fox stag owl viper crow dove falcon kraken leviathan
spell ritual incantation prayer hymn chant rhythm dance duel tournament crown
heir bastard orphan veteran captain admiral general soldier mercenary bandit
pirate smuggler thief bard poet scribe sage hermit monk nun priest saint
relic forbidden sealed awakened reborn revenant lich vampire werewolf fae
nymph sylph gnome kobold goblin troll ogre minotaur centaur hydra chimera
griffin unicorn basilisk manticore dream memory mirror glass veil gate-keeper
""".split()

TAG_NAMES = [
    'Action', 'Adventure', 'Romance', 'Fantasy', 'Isekai', 'Harem', 'Comedy',
    'Drama', 'Mystery', 'Horror', 'Psychological', 'Tragedy', 'Slice of Life',
    'Sci-fi', 'Cultivation', 'Martial Arts', 'Xianxia', 'Xuanhuan', 'Wuxia',
    'System', 'Reincarnation', 'Transmigration', 'Time Travel', 'Dungeons',
    'Monsters', 'Magic', 'Swordplay', 'Kingdom Building', 'Politics', 'War',
    'Military', 'School Life', 'Campus', 'Office', 'Workplace', 'Sports',
    'Music', 'Gore', 'Survival', 'Post-apocalyptic', 'Zombies', 'Vampires',
    'Werewolves', 'Demons', 'Angels', 'Gods', 'Villainess', 'Overpowered MC',
    'Strategic', 'Anti-hero', 'Dark', 'Light Novel', 'Web Novel', 'Historical',
    'Royalty', 'Nobles', 'Revenge', 'Regression', 'Level Up', 'Crafting',
    'Gamer', 'Virtual Reality', 'Mecha', 'Cyberpunk', 'Steampunk', 'Pets',
    'Found Family', 'Slow Burn', 'Enemies to Lovers', 'Female Protagonist',
    'Male Protagonist', 'Multiple POV', 'Non-human', 'Shapeshifters', 'Heroes',
    'Mythology', 'Gods and Goddesses', 'Erotica', 'Ecchi', 'Mature',
]
R18_TAGS = {'Erotica', 'Ecchi', 'Mature'}

LANGUAGES = ['fr', 'es', 'pt', 'id', 'ru', 'zh']
STATUSES = ['Ongoing', 'Completed', 'Unknown', 'On Hiatus', 'Cancelled']
REACTIONS = ['sparkle', 'heart', 'laugh', 'eyebrow', 'lightbulb', 'write', 'paint', 'sick']
VOCAB_SQL = 'ARRAY[' + ','.join(f"'{w}'" for w in VOCAB) + ']::text[]'


class Command(BaseCommand):
    # System checks would connect to the bench DB before handle() creates it.
    requires_system_checks = []
    help = (
        'Build a deterministic benchmark database (run against POSTGRES_DB=lncrawler_bench). '
        'Scale 1.0 is about 20M chapters and roughly 10 GB; use --scale 0.01 for a quick run.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--scale', type=float, default=1.0, help='Fraction of the 1.0 row counts')
        parser.add_argument('--seed', type=int, default=42, help='Salt for all generated values')
        parser.add_argument('--reset', action='store_true', help='Drop and recreate the bench database first')
        parser.add_argument('--skip-files', action='store_true', help='Do not write chapter body files')
        parser.add_argument(
            '--yes-i-know', action='store_true',
            help="Allow a database name without 'bench' (use with care: --reset drops it)",
        )

    # ----- helpers that build SQL expressions -------------------------------

    def _h(self, key):
        """Non-negative int hash of a SQL text expression, salted with the seed."""
        return f"(hashtext('{self.seed}-' || ({key})::text) & 2147483647)"

    def _u(self, key):
        """Uniform float in [0, 1) from a SQL text expression."""
        return f"({self._h(key)}::float8 / 2147483648.0)"

    def _w(self, key):
        """One vocabulary word picked from a hash."""
        return f"({VOCAB_SQL})[1 + {self._h(key)} % {len(VOCAB)}]"

    def _words(self, key, count_sql):
        """Space-joined vocabulary words; count_sql is the number of words."""
        return (
            f"(SELECT string_agg({self._w(key + ' || k::text')}, ' ') "
            f"FROM generate_series(1, {count_sql}) k)"
        )

    def _novel_pick(self, key):
        """Novel number 1..novels, skewed toward low numbers (popular novels)."""
        return f"LEAST({self.c['novels']}, 1 + floor(power({self._u(key)}, 3) * {self.c['novels']})::int)"

    def _user_pick(self, key):
        """User id 1..users: 80% of picks go to the first 20% of users."""
        users = self.c['users']
        top = max(1, int(users * 0.2))
        return (
            f"CASE WHEN {self._u(key + " || 'a'")} < 0.8 "
            f"THEN 1 + floor({self._u(key + " || 'b'")} * {top})::int "
            f"ELSE {top} + 1 + floor({self._u(key + " || 'b'")} * {users - top})::int END"
        )

    def _ip(self, key):
        return (
            f"format('10.%s.%s.%s', {self._h(key + " || 'i1'")} % 256, "
            f"{self._h(key + " || 'i2'")} % 256, {self._h(key + " || 'i3'")} % 256)::inet"
        )

    def _username(self, uid):
        return f"CASE WHEN {uid} = 1 THEN 'bench_heavy' ELSE 'bench_user_' || {uid} END"

    def _novel_uuid(self, n):
        return f"md5('bench-novel-' || {n})::uuid"

    # ----- command entry ----------------------------------------------------

    def handle(self, *args, **options):
        scale = options['scale']
        if scale <= 0:
            raise CommandError('--scale must be greater than 0')
        name = connection.settings_dict['NAME']
        if 'bench' not in name and not options['yes_i_know']:
            raise CommandError(
                f"Refusing to seed database {name!r}: the name lacks 'bench'. "
                "Use POSTGRES_DB=lncrawler_bench, or pass --yes-i-know."
            )
        if not re.fullmatch(r'[A-Za-z0-9_]+', name):
            raise CommandError(f'Unsupported database name {name!r}')

        self.seed = options['seed']
        self.scale = scale
        self.timings = []
        self.c = self._counts(scale)
        started = time.perf_counter()

        connection.close()
        self._create_database(name, options['reset'])
        self.stdout.write(f'Migrating {name} ...')
        call_command('migrate', interactive=False, verbosity=0)

        with connection.cursor() as cur:
            cur.execute('SELECT EXISTS (SELECT 1 FROM lncrawler_api_novel) OR '
                        'EXISTS (SELECT 1 FROM auth_app_customuser)')
            has_rows = cur.fetchone()[0]
        if has_rows and not options['reset']:
            raise CommandError(
                f'{name} already holds rows. Rerun with --reset to drop and rebuild it: '
                f'docker exec -e POSTGRES_DB={name} lncrawler-api-1 python manage.py seed_bench '
                f'--scale {scale} --reset'
            )

        self.stdout.write(f'Seeding {name} at scale {scale}: {self._describe()}')
        with connection.cursor() as cur:
            cur.execute('SET synchronous_commit = off')
            try:
                cur.execute('SET session_replication_role = replica')
            except Exception as exc:  # not superuser: keep FK triggers on
                self.stdout.write(f'note: session_replication_role not set ({exc}); FK triggers stay on')

        self._build()
        if not options['skip_files']:
            self._write_files()
        self._finish(name, time.perf_counter() - started)

    def _counts(self, scale):
        def scaled(base, minimum=1):
            return max(minimum, int(round(base * scale)))

        novels = scaled(10000)
        sources = max(scaled(20000), 2 * novels)
        chapters_sources = sources
        return {
            'users': scaled(50000),
            'novels': novels,
            'sources': sources,
            'externals': EXTERNAL_COUNT,
            'tags': scaled(1500, 20),
            'tag_aliases': scaled(3000),
            'authors': scaled(8000),
            'author_aliases': scaled(2000),
            'alt_titles': scaled(15000),
            'editors': scaled(500),
            'translators': scaled(1500),
            'ratings': scaled(300000),
            'reviews': scaled(30000),
            'reactions': scaled(60000),
            'comments': scaled(1000000),
            'comment_votes': scaled(500000),
            'source_votes': scaled(200000),
            'folders': scaled(100000),
            'bookmarks': scaled(500000),
            'history': scaled(1000000),
            'reading_lists': scaled(20000),
            'list_items': scaled(200000),
            'list_collaborators': scaled(5000),
            'pinned': scaled(50000),
            'friendships': scaled(200000),
            'reader_slots': scaled(20000),
            'chat': scaled(50000),
            'jobs': scaled(10000),
            'audiobooks': min(novels, scaled(200)),
            'listening': scaled(10000),
            'chapter_sources': chapters_sources,
        }

    def _describe(self):
        keys = ['users', 'novels', 'sources', 'tags', 'comments', 'history', 'chapter_sources']
        return ', '.join(f'{k}={self.c[k]:,}' for k in keys)

    def _create_database(self, name, reset):
        db = connection.settings_dict
        with psycopg.connect(
            host=db['HOST'] or 'localhost',
            port=db['PORT'] or 5432,
            user=db['USER'],
            password=db['PASSWORD'],
            dbname='postgres',
            autocommit=True,
        ) as admin:
            exists = admin.execute(
                'SELECT 1 FROM pg_database WHERE datname = %s', [name]
            ).fetchone() is not None
            if reset and exists:
                admin.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
                self.stdout.write(f'Dropped {name}')
                exists = False
            if not exists:
                admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
                self.stdout.write(f'Created {name}')

    def _exec(self, statement):
        with connection.cursor() as cur:
            cur.execute(statement)

    def _stage(self, label, statement, heavy=False):
        """Run one bulk statement (committed on return) and print its row count and time."""
        started = time.perf_counter()
        with connection.cursor() as cur:
            if heavy:
                with transaction.atomic():
                    cur.execute("SET LOCAL work_mem = '256MB'")
                    cur.execute(statement)
            else:
                cur.execute(statement)
            rows = cur.rowcount
        elapsed = time.perf_counter() - started
        self.timings.append((label, rows, elapsed))
        self.stdout.write(f'{label:<28} {rows:>13,} rows {elapsed:>10.1f}s')
        return rows

    def _scalar(self, statement):
        with connection.cursor() as cur:
            cur.execute(statement)
            return cur.fetchone()[0]

    # ----- stages -----------------------------------------------------------

    def _build(self):
        c = self.c
        rng = random.Random(self.seed)

        self._stage('users', self._sql_users())
        self._stage('external sources', self._sql_externals())
        self._exec(
            'CREATE TEMP TABLE tmp_ext AS SELECT (row_number() OVER (ORDER BY id) - 1)::int AS idx, '
            'id, source_name FROM lncrawler_api_externalsource'
        )
        self._python_small_tables(rng)
        self._stage('novels', self._sql_novels(), heavy=True)
        self._sql_plan_and_sources()
        self._sql_source_links()
        self._stage('weekly source views', self._sql_weekly_views(), heavy=True)
        self._stage('novel similarities', self._sql_similarities())
        self._chapters_and_volumes()
        self._comments_and_votes()
        self._ratings_and_reviews()
        self._library_and_history()
        self._lists_social_reader_chat()
        self._stage('jobs', self._sql_jobs())
        self._audiobooks()

    def _python_small_tables(self, rng):
        """Tags, authors, editors, translators and alt titles: bulk_create with normalized keys."""
        c = self.c
        tags, seen = [], set()
        names = list(TAG_NAMES)
        index = 0
        while len(tags) < c['tags']:
            name = names[index] if index < len(names) else f'tag-{index}'
            index += 1
            key = normalize_tag(name)
            if key in seen:
                continue
            seen.add(key)
            # Few adult tags, like prod: the named R18 ones plus every 300th filler.
            is_adult = name in R18_TAGS or len(tags) % 300 == 299
            tags.append(Tag(name=name, normalized=key, is_adult=is_adult))
        created_tags = Tag.objects.bulk_create(tags, batch_size=5000)
        tag_pks = [t.pk for t in created_tags]
        self.tag_ids_sql = 'ARRAY[' + ','.join(str(p) for p in tag_pks) + ']::bigint[]'
        self.c['tag_count'] = len(tag_pks)

        aliases = []
        for i in range(c['tag_aliases']):
            target = created_tags[i % len(created_tags)]
            alias_name = f'{target.name} alias {i}'
            aliases.append(TagAlias(name=alias_name, normalized=normalize_tag(alias_name), tag=target))
        TagAlias.objects.bulk_create(aliases, batch_size=5000)
        self.stdout.write(f"{'tags + aliases':<28} {len(tag_pks) + len(aliases):>13,} rows")

        authors = []
        for i in range(c['authors']):
            name = f"{rng.choice(VOCAB).title()} {rng.choice(VOCAB).title()} {i}"
            authors.append(Author(name=name, normalized=normalize_author(name)))
        created_authors = Author.objects.bulk_create(authors, batch_size=5000)
        self.author_ids_sql = 'ARRAY[' + ','.join(str(a.pk) for a in created_authors) + ']::bigint[]'
        author_aliases = []
        for i in range(c['author_aliases']):
            target = created_authors[i % len(created_authors)]
            alias_name = f'{target.name} (alt {i})'
            author_aliases.append(AuthorAlias(name=alias_name, normalized=normalize_author(alias_name), author=target))
        AuthorAlias.objects.bulk_create(author_aliases, batch_size=5000)
        self.stdout.write(f"{'authors + aliases':<28} {len(created_authors) + len(author_aliases):>13,} rows")

        editors = Editor.objects.bulk_create(
            [Editor(name=f'Editor {rng.choice(VOCAB).title()} {i}') for i in range(c['editors'])],
            batch_size=5000,
        )
        translators = Translator.objects.bulk_create(
            [Translator(name=f'Translator {rng.choice(VOCAB).title()} {i}') for i in range(c['translators'])],
            batch_size=5000,
        )
        self.editor_ids_sql = 'ARRAY[' + ','.join(str(e.pk) for e in editors) + ']::bigint[]'
        self.translator_ids_sql = 'ARRAY[' + ','.join(str(t.pk) for t in translators) + ']::bigint[]'
        self.stdout.write(f"{'editors + translators':<28} {len(editors) + len(translators):>13,} rows")

        titles = [
            AlternativeTitle(name=f"{rng.choice(VOCAB).title()} {rng.choice(VOCAB).title()} alt {i}")
            for i in range(c['alt_titles'])
        ]
        alt = AlternativeTitle.objects.bulk_create(titles, batch_size=5000)
        self.alt_ids_sql = 'ARRAY[' + ','.join(str(a.pk) for a in alt) + ']::bigint[]'
        self.stdout.write(f"{'alternative titles':<28} {len(alt):>13,} rows")

    def _sql_users(self):
        n = self.c['users']
        return f"""
INSERT INTO auth_app_customuser (username, email, password, is_superuser, first_name, last_name,
    is_staff, is_active, date_joined, word_read, preferred_ui_language, preferred_languages,
    language_filter_enabled, bio, privacy_settings, social_links, discoverable, show_r18)
SELECT {self._username('i')},
    {self._username('i')} || '@bench.invalid',
    '!' || md5(i::text) || md5('pw' || i::text),
    false, '', '', false, true,
    now() - (({self._h("i::text || 'joined'")}) % 1095) * interval '1 day',
    0, '', '[]'::jsonb, true, '', '{{}}'::jsonb, '{{}}'::jsonb, true, 'blur'
FROM generate_series(1, {n}) AS g(i)
ORDER BY i
"""

    def _sql_externals(self):
        return f"""
INSERT INTO lncrawler_api_externalsource (source_name, status)
SELECT 'bench-source-' || lpad(i::text, 2, '0'), 'alive'
FROM generate_series(1, {EXTERNAL_COUNT}) AS g(i)
ORDER BY i
"""

    def _sql_novels(self):
        n_novels = self.c['novels']
        nw = self._h("n::text || 'nw'")
        self._exec(f"""
CREATE TEMP TABLE tmp_nov AS
SELECT n, md5('bench-novel-' || n)::uuid AS nid, title,
       lower(regexp_replace(title, '[^A-Za-z0-9]+', '-', 'g')) || '-' || n AS slug,
       now() - (({self._h("n::text || 'created'")}) % 1826) * interval '1 day' AS created_at
FROM (
    SELECT n, initcap(array_to_string(ws[1:nw], ' ')) AS title
    FROM (
        SELECT n, 2 + {nw} % 4 AS nw,
               ARRAY[{self._w("n::text || 'w1'")}, {self._w("n::text || 'w2'")}, {self._w("n::text || 'w3'")},
                     {self._w("n::text || 'w4'")}, {self._w("n::text || 'w5'")}] AS ws
        FROM generate_series(1, {n_novels}) AS g(n)
    ) base
) titled
""")
        return f"""
INSERT INTO lncrawler_api_novel (id, title, slug, created_at, updated_at, novel_path, comment_count,
    is_dmca, rank_total_views, rank_week_views, rank_avg_rating, added_by_id)
SELECT nid, title, slug, created_at, created_at, 'bench/' || slug, 0,
       {self._u("n::text || 'dmca'")} < 0.01, 0, 0, 0,
       CASE WHEN {self._h("n::text || 'added'")} % 10 < 7 THEN {self._user_pick("n::text || 'addby'")} END
FROM tmp_nov
ORDER BY n
"""

    def _sql_plan_and_sources(self):
        n_novels = self.c['novels']
        extra = self.c['sources'] - n_novels
        self._exec(f"""
CREATE TEMP TABLE tmp_plan AS
SELECT n, 0 AS j, n AS sid FROM generate_series(1, {n_novels}) AS g(n)
""")
        if extra > 0:
            self._exec(f"""
CREATE TEMP TABLE tmp_extra AS
SELECT k, n, rn AS j FROM (
    SELECT k, n, row_number() OVER (PARTITION BY n ORDER BY k) AS rn
    FROM (
        SELECT k, CASE WHEN {self._u("k::text || 'mix'")} < 0.5
                       THEN {self._novel_pick("k::text || 'ex'")}
                       ELSE 1 + {self._h("k::text || 'uni'")} % {n_novels} END AS n
        FROM generate_series(1, {extra * 6}) AS g(k)
    ) cand
) ranked
WHERE rn <= 3
ORDER BY k
LIMIT {extra}
""")
            self._exec(f"""
INSERT INTO tmp_plan (n, j, sid)
SELECT n, j, {n_novels} + row_number() OVER (ORDER BY k) FROM tmp_extra
""")
        self.stdout.write(
            f"{'extra source plan':<28} {self._scalar('SELECT count(*) FROM tmp_plan') - n_novels:>13,} rows"
        )
        self.c['sources'] = self._scalar('SELECT count(*) FROM tmp_plan')
        self._exec('CREATE TEMP TABLE tmp_nov_i AS SELECT n, nid, title, slug FROM tmp_nov')
        return self._stage('sources', self._sources_insert_sql(), heavy=True)

    def _sources_insert_sql(self):
        return f"""
INSERT INTO lncrawler_api_novelfromsource (novel_id, title, source_url, external_source_id, source_slug,
    language, status, synopsis, is_adult, adult_from_source, created_at, updated_at, last_chapter_update,
    source_version, total_views, upvotes, downvotes, edition, cover_url, source_path, cover_path,
    cover_min_path, overview_picture_path, original_publisher, english_publisher, novelupdates_url,
    meta_file_path, cover_phash)
SELECT nv.nid, nv.title,
    'https://' || e.source_name || '.example/novel/' || nv.slug,
    e.id, e.source_name,
    CASE WHEN {self._u("p.sid::text || 'lang'")} < 0.85 THEN 'en'
         ELSE (ARRAY{LANGUAGES})[1 + {self._h("p.sid::text || 'lang2'")} % {len(LANGUAGES)}] END,
    CASE WHEN {self._u("p.sid::text || 'st'")} < 0.6 THEN 'Ongoing'
         WHEN {self._u("p.sid::text || 'st'")} < 0.85 THEN 'Completed'
         WHEN {self._u("p.sid::text || 'st'")} < 0.92 THEN 'Unknown'
         WHEN {self._u("p.sid::text || 'st'")} < 0.97 THEN 'On Hiatus'
         ELSE 'Cancelled' END,
    {self._words("p.sid::text || 'syn'", f"40 + {self._h('p.sid::text || ' + repr('synlen'))} % 80")},
    {self._u("p.sid::text || 'adult'")} < 0.03,
    {self._u("p.sid::text || 'adult'")} < 0.03,
    now() - (({self._h("p.sid::text || 'cr'")}) % 1000) * interval '1 day',
    now() - (({self._h("p.sid::text || 'cr'")}) % 1000) * interval '1 day',
    now() - (730 * sqrt(p.n::float8 / {self.c['novels']}) * {self._u("p.sid::text || 'lcu'")}) * interval '1 day',
    1 + {self._h("p.sid::text || 'ver'")} % 5, 0, 0, 0, '',
    NULL, '{SOURCE_PATH}', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM tmp_plan p
JOIN tmp_nov_i nv ON nv.n = p.n
JOIN tmp_ext e ON e.idx = (p.n + 7 * p.j) % {EXTERNAL_COUNT}
ORDER BY p.sid
"""

    def _sql_source_links(self):
        """Tags (~8 picks per source, skewed to the named genres like prod), authors (1-2), editors (~30%), translators and alt titles (~1)."""
        self._stage('source-tag links', f"""
INSERT INTO lncrawler_api_novelfromsource_tags (novelfromsource_id, tag_id)
SELECT s.id, ({self.tag_ids_sql})[1 + floor(power({self._u("s.id::text || 'tg' || k::text")}, 3) * {self.c['tag_count']})::int]
FROM lncrawler_api_novelfromsource s
CROSS JOIN generate_series(1, 8) AS g(k)
ON CONFLICT DO NOTHING
""", heavy=True)
        self._stage('source-author links', f"""
INSERT INTO lncrawler_api_novelfromsource_authors (novelfromsource_id, author_id)
SELECT s.id, ({self.author_ids_sql})[1 + {self._h("s.id::text || 'au' || k::text")} % {self.c['authors']}]
FROM lncrawler_api_novelfromsource s
CROSS JOIN generate_series(1, 2) AS g(k)
WHERE k <= 1 + {self._h("s.id::text || 'aun'")} % 2
ON CONFLICT DO NOTHING
""")
        self._stage('source-editor links', f"""
INSERT INTO lncrawler_api_novelfromsource_editors (novelfromsource_id, editor_id)
SELECT s.id, ({self.editor_ids_sql})[1 + {self._h("s.id::text || 'ed'")} % {self.c['editors']}]
FROM lncrawler_api_novelfromsource s
WHERE {self._u("s.id::text || 'edh'")} < 0.3
ON CONFLICT DO NOTHING
""")
        self._stage('source-translator links', f"""
INSERT INTO lncrawler_api_novelfromsource_translators (novelfromsource_id, translator_id)
SELECT s.id, ({self.translator_ids_sql})[1 + {self._h("s.id::text || 'tr'")} % {self.c['translators']}]
FROM lncrawler_api_novelfromsource s
ON CONFLICT DO NOTHING
""")
        self._stage('source-alt title links', f"""
INSERT INTO lncrawler_api_novelfromsource_alternative_titles (novelfromsource_id, alternativetitle_id)
SELECT s.id, ({self.alt_ids_sql})[1 + {self._h("s.id::text || 'alt'")} % {self.c['alt_titles']}]
FROM lncrawler_api_novelfromsource s
WHERE {self._u("s.id::text || 'alth'")} < 0.95
ON CONFLICT DO NOTHING
""")

    def _sql_weekly_views(self):
        """30 daily rows per source for the last 30 days, plus 8 weekly rows before that."""
        sources = self.c['sources']
        self._exec(f"""
INSERT INTO lncrawler_api_weeklysourceview (source_id, day, granularity, views)
SELECT s.id, current_date - d, 'day',
       1 + {self._h("s.id::text || 'vd' || d::text")} % 50
           + CASE WHEN s.id <= {max(1, sources // 10)} THEN 200 ELSE 0 END
FROM lncrawler_api_novelfromsource s
CROSS JOIN generate_series(0, 29) AS g(d)
""")
        return f"""
INSERT INTO lncrawler_api_weeklysourceview (source_id, day, granularity, views)
SELECT s.id, date_trunc('week', current_date - 30 - 7 * k)::date, 'week',
       100 + {self._h("s.id::text || 'vw' || k::text")} % 5000
FROM lncrawler_api_novelfromsource s
CROSS JOIN generate_series(1, 8) AS g(k)
"""

    def _sql_similarities(self):
        n_novels = self.c['novels']
        if n_novels < 2:
            return 'SELECT 1 WHERE false'
        return f"""
INSERT INTO lncrawler_api_novelsimilarity (from_novel_id, to_novel_id, similarity)
SELECT md5('bench-novel-' || n)::uuid,
       md5('bench-novel-' || (1 + (n + 1 + {self._h("n::text || 'sim' || k::text")} % {n_novels - 1} - 1) % {n_novels}))::uuid,
       {self._u("n::text || 'simv' || k::text")}
FROM generate_series(1, {n_novels}) AS a(n)
CROSS JOIN generate_series(1, 10) AS b(k)
ON CONFLICT DO NOTHING
"""

    def _chapters_and_volumes(self):
        """Chapters per source: exponential-ish (mean ~1000, 20..12000), inserted 500 sources per statement."""
        force = self.scale >= 0.01
        self._exec(f"""
CREATE TEMP TABLE tmp_src AS
SELECT s.id AS source_id, e.source_name AS ext_name, nv.slug AS novel_slug,
       CASE WHEN s.id <= {FORCED_SOURCES} AND {str(force).lower()} THEN 12000
            ELSE least(12000, greatest(20, (-1000 * ln(1 - {self._u("s.id::text || 'cnt'")}))::int))
       END AS cnt
FROM lncrawler_api_novelfromsource s
JOIN tmp_nov_i nv ON nv.nid = s.novel_id
JOIN tmp_ext e ON e.id = s.external_source_id
""")
        total_sources = self.c['sources']
        total_chapters = self._scalar('SELECT sum(cnt) FROM tmp_src')
        started = time.perf_counter()
        done = 0
        self.stdout.write(f"{'chapters':<28} planned {total_chapters:,} rows in {total_sources} sources")
        for lo in range(1, total_sources + 1, 500):
            hi = min(total_sources, lo + 499)
            with connection.cursor() as cur:
                cur.execute(f"""
INSERT INTO lncrawler_api_chapter (novel_from_source_id, chapter_id, url, title, volume, volume_title,
    images, has_content, word_count)
SELECT t.source_id, g.cid,
    'https://' || t.ext_name || '.example/' || t.novel_slug || '/chapter-' || g.cid,
    'Chapter ' || g.cid || ': ' || initcap(array_to_string(
        (ARRAY[{self._w("t.source_id::text || '-' || g.cid::text || 'c1'")},
              {self._w("t.source_id::text || '-' || g.cid::text || 'c2'")},
              {self._w("t.source_id::text || '-' || g.cid::text || 'c3'")},
              {self._w("t.source_id::text || '-' || g.cid::text || 'c4'")}])
        [1:2 + {self._h("t.source_id::text || '-' || g.cid::text || 'cn'")} % 3], ' ')),
    (g.cid - 1) / 100 + 1,
    'Volume ' || ((g.cid - 1) / 100 + 1),
    CASE WHEN {self._h("t.source_id::text || '-' || g.cid::text || 'im'")} % 200 = 0
         THEN ARRAY['img-' || g.cid || '-1.jpg']::varchar[] ELSE '{{}}'::varchar[] END,
    {self._h("t.source_id::text || '-' || g.cid::text || 'hc'")} % 100 < 98,
    1500 + {self._h("t.source_id::text || '-' || g.cid::text || 'wc'")} % 2001
FROM tmp_src t
CROSS JOIN LATERAL generate_series(1, t.cnt) AS g(cid)
WHERE t.source_id BETWEEN {lo} AND {hi}
ORDER BY t.source_id, g.cid
""")
                done += cur.rowcount
            elapsed = time.perf_counter() - started
            rate = done / elapsed if elapsed else 0
            self.stdout.write(
                f"  chapters {hi:>7,}/{total_sources:,} sources  {done:>12,} rows  "
                f"{elapsed:>8.1f}s  {rate:>10,.0f} rows/s"
            )
        self.timings.append(('chapters', done, time.perf_counter() - started))
        self._stage('volumes', """
INSERT INTO lncrawler_api_volume (novel_from_source_id, volume_id, title, start_chapter, final_chapter, chapter_count)
SELECT t.source_id, v, 'Volume ' || v, (v - 1) * 100 + 1, least(v * 100, t.cnt),
       least(v * 100, t.cnt) - ((v - 1) * 100 + 1) + 1
FROM tmp_src t
CROSS JOIN LATERAL generate_series(1, (t.cnt + 99) / 100) AS g(v)
""")
        self._exec("""
CREATE TEMP TABLE tmp_first AS
SELECT p.n, p.sid, t.cnt FROM tmp_plan p JOIN tmp_src t ON t.source_id = p.sid WHERE p.j = 0
""")
        self._exec(f"""
CREATE TEMP TABLE tmp_en AS
SELECT DISTINCT ON (p.n) p.n, p.sid
FROM tmp_plan p JOIN lncrawler_api_novelfromsource s ON s.id = p.sid
WHERE s.language = 'en'
ORDER BY p.n, p.sid
""")

    def _comments_and_votes(self):
        c = self.c
        total = c['comments']
        top_novel = int(round(total * 0.3 * 0.85))
        top_chapter = int(round(total * 0.7 * 0.85))
        replies = total - top_novel - top_chapter
        self.comment_top_total = top_novel + top_chapter
        n_novels = c['novels']
        s_count = c['sources']

        self._stage('comments on novels', f"""
INSERT INTO lncrawler_api_comment (id, novel_id, chapter_id, user_id, author_name, message, contains_spoiler,
    created_at, ip_address, edited, upvotes, downvotes)
SELECT gen_random_uuid(), {self._novel_uuid(self._novel_pick("k::text || 'cn'"))}, NULL,
       CASE WHEN {self._h("k::text || 'cma'")} % 10 = 0 THEN NULL ELSE {self._user_pick("k::text || 'cu'")} END,
       CASE WHEN {self._h("k::text || 'cma'")} % 10 = 0 THEN 'Anonymous'
            ELSE CASE WHEN {self._user_pick("k::text || 'cu'")} = 1 THEN 'bench_heavy'
                      ELSE 'bench_user_' || {self._user_pick("k::text || 'cu'")} END END,
       {self._words("g.k::text || 'cmsg'", f"6 + {self._h('k::text || ' + repr('cmlen'))} % 10")},
       {self._h("k::text || 'cspoil'")} % 20 = 0,
       now() - {self._u("k::text || 'cts'")} * 365 * interval '1 day',
       CASE WHEN {self._h("k::text || 'cma'")} % 10 = 0 THEN {self._ip("k::text || 'cip'")} END,
       false, 0, 0
FROM generate_series(1, {top_novel}) AS g(k)
""", heavy=True)
        self._stage('comments on chapters', f"""
WITH p AS (
    SELECT k,
           1 + floor(power({self._u("k::text || 'ccs'")}, 3) * {s_count})::int AS s
    FROM generate_series(1, {top_chapter}) AS g(k)
), q AS (
    SELECT p.k, p.s, 1 + floor(t.cnt * power({self._u("p.k::text || 'ccc'")}, 2))::int AS cid
    FROM p JOIN tmp_src t ON t.source_id = p.s
)
INSERT INTO lncrawler_api_comment (id, novel_id, chapter_id, user_id, author_name, message, contains_spoiler,
    created_at, ip_address, edited, upvotes, downvotes)
SELECT gen_random_uuid(), NULL, ch.id,
       CASE WHEN {self._h("q.k::text || 'cha'")} % 10 = 0 THEN NULL ELSE {self._user_pick("q.k::text || 'cu2'")} END,
       CASE WHEN {self._h("q.k::text || 'cha'")} % 10 = 0 THEN 'Anonymous'
            ELSE CASE WHEN {self._user_pick("q.k::text || 'cu2'")} = 1 THEN 'bench_heavy'
                      ELSE 'bench_user_' || {self._user_pick("q.k::text || 'cu2'")} END END,
       {self._words("q.k::text || 'chm'", f"6 + {self._h('q.k::text || ' + repr('chlen'))} % 10")},
       {self._h("q.k::text || 'chs'")} % 20 = 0,
       now() - {self._u("q.k::text || 'chts'")} * 365 * interval '1 day',
       CASE WHEN {self._h("q.k::text || 'cha'")} % 10 = 0 THEN {self._ip("q.k::text || 'chip'")} END,
       false, 0, 0
FROM q
JOIN lncrawler_api_chapter ch ON ch.novel_from_source_id = q.s AND ch.chapter_id = q.cid
""", heavy=True)
        self._exec(f"""
CREATE TEMP TABLE tmp_ctop AS
SELECT row_number() OVER (ORDER BY id) AS rn, id, novel_id, chapter_id, created_at
FROM lncrawler_api_comment WHERE parent_id IS NULL
""")
        self._stage('comment replies', f"""
INSERT INTO lncrawler_api_comment (id, novel_id, chapter_id, parent_id, user_id, author_name, message,
    contains_spoiler, created_at, ip_address, edited, upvotes, downvotes)
SELECT gen_random_uuid(), p.novel_id, p.chapter_id, p.id,
       CASE WHEN {self._h("r.k::text || 'rpa'")} % 10 = 0 THEN NULL ELSE {self._user_pick("r.k::text || 'ru'")} END,
       CASE WHEN {self._h("r.k::text || 'rpa'")} % 10 = 0 THEN 'Anonymous'
            ELSE CASE WHEN {self._user_pick("r.k::text || 'ru'")} = 1 THEN 'bench_heavy'
                      ELSE 'bench_user_' || {self._user_pick("r.k::text || 'ru'")} END END,
       {self._words("r.k::text || 'rm'", "6 + 3")},
       false,
       LEAST(now(), p.created_at + ({self._h("r.k::text || 'rts'")} % 720) * interval '1 hour'),
       CASE WHEN {self._h("r.k::text || 'rpa'")} % 10 = 0 THEN {self._ip("r.k::text || 'rip'")} END,
       false, 0, 0
FROM generate_series(1, {replies}) AS r(k)
JOIN tmp_ctop p ON p.rn = 1 + {self._h("r.k::text || 'rpick'")} % {self.comment_top_total}
""", heavy=True)
        comment_total = self._scalar('SELECT count(*) FROM lncrawler_api_comment')
        self._exec(f"""
CREATE TEMP TABLE tmp_cids AS
SELECT row_number() OVER (ORDER BY id) AS rn, id FROM lncrawler_api_comment
""")
        self._stage('comment votes', f"""
INSERT INTO lncrawler_api_commentvote (comment_id, ip_address, vote_type, created_at, updated_at)
SELECT c.id, {self._ip("v.k::text || 'vip'")},
       CASE WHEN {self._u("v.k::text || 'vt'")} < 0.8 THEN 'up' ELSE 'down' END,
       now() - {self._u("v.k::text || 'vts'")} * 100 * interval '1 day',
       now()
FROM generate_series(1, {c['comment_votes']}) AS v(k)
JOIN tmp_cids c ON c.rn = 1 + floor(power({self._u("v.k::text || 'vc'")}, 2) * {comment_total})::int
ON CONFLICT DO NOTHING
""", heavy=True)
        self._stage('source votes', f"""
INSERT INTO lncrawler_api_sourcevote (source_id, ip_address, vote_type, created_at, updated_at)
SELECT s.sid, {self._ip("v.k::text || 'svip'")},
       CASE WHEN {self._u("v.k::text || 'svt'")} < 0.85 THEN 'up' ELSE 'down' END,
       now() - {self._u("v.k::text || 'svts'")} * 365 * interval '1 day', now()
FROM generate_series(1, {c['source_votes']}) AS v(k)
JOIN LATERAL (SELECT 1 + floor(power({self._u("v.k::text || 'svs'")}, 3) * {s_count})::int AS sid) s ON true
ON CONFLICT DO NOTHING
""", heavy=True)
        self._exec(f"""
UPDATE lncrawler_api_comment c
SET upvotes = x.up, downvotes = x.down
FROM (
    SELECT comment_id,
           count(*) FILTER (WHERE vote_type = 'up') AS up,
           count(*) FILTER (WHERE vote_type = 'down') AS down
    FROM lncrawler_api_commentvote GROUP BY comment_id
) x
WHERE c.id = x.comment_id
""")
        self._exec(f"""
UPDATE lncrawler_api_novelfromsource s
SET upvotes = x.up, downvotes = x.down
FROM (
    SELECT source_id,
           count(*) FILTER (WHERE vote_type = 'up') AS up,
           count(*) FILTER (WHERE vote_type = 'down') AS down
    FROM lncrawler_api_sourcevote GROUP BY source_id
) x
WHERE s.id = x.source_id
""")
        self.comment_total = comment_total

    def _ratings_and_reviews(self):
        c = self.c
        self._stage('novel ratings', f"""
INSERT INTO lncrawler_api_novelrating (novel_id, user_id, ip_address, rating, created_at, updated_at)
SELECT {self._novel_uuid(self._novel_pick("r.k::text || 'rn'"))}, {self._user_pick("r.k::text || 'ru'")},
       NULL, 1 + {self._h("r.k::text || 'rv'")} % 5,
       now() - {self._u("r.k::text || 'rts'")} * 365 * interval '1 day', now()
FROM generate_series(1, {c['ratings']}) AS r(k)
ON CONFLICT DO NOTHING
""", heavy=True)
        heavy_reviews = min(300, c['novels'])
        self._stage('reviews', f"""
INSERT INTO lncrawler_api_review (id, novel_id, user_id, title, content, rating, created_at, updated_at)
SELECT gen_random_uuid(), {self._novel_uuid('g.n')}, 1,
       'Review ' || initcap({self._w("g.n::text || 'hrt'")}),
       {self._words("g.n::text || 'hrc'", "20")}, 1 + {self._h("g.n::text || 'hrr'")} % 5, now(), now()
FROM generate_series(1, {heavy_reviews}) AS g(n)
ON CONFLICT DO NOTHING
""")
        self._stage('reviews', f"""
INSERT INTO lncrawler_api_review (id, novel_id, user_id, title, content, rating, created_at, updated_at)
SELECT gen_random_uuid(), {self._novel_uuid(self._novel_pick("g.k::text || 'rvn'"))},
       {self._user_pick("g.k::text || 'rvu'")},
       'Review ' || initcap({self._w("g.k::text || 'rvt'")}),
       {self._words("g.k::text || 'rvc'", f"20 + {self._h('g.k::text || ' + repr('rvlen'))} % 40")},
       1 + {self._h("g.k::text || 'rvr'")} % 5,
       now() - {self._u("g.k::text || 'rvts'")} * 365 * interval '1 day', now()
FROM generate_series(1, {c['reviews']}) AS g(k)
ON CONFLICT DO NOTHING
""", heavy=True)
        review_total = self._scalar('SELECT count(*) FROM lncrawler_api_review')
        self._exec("""
CREATE TEMP TABLE tmp_rev AS SELECT row_number() OVER (ORDER BY id) AS rn, id FROM lncrawler_api_review
""")
        reactions = ', '.join(f"'{r}'" for r in REACTIONS)
        self._stage('review reactions', f"""
INSERT INTO lncrawler_api_reviewreaction (id, review_id, user_id, ip_address, reaction, created_at)
SELECT gen_random_uuid(), rv.id,
       CASE WHEN {self._u("g.k::text || 'rxa'")} < 0.8 THEN {self._user_pick("g.k::text || 'rxu'")} END,
       {self._ip("g.k::text || 'rxip'")},
       (ARRAY[{reactions}])[1 + {self._h("g.k::text || 'rxr'")} % {len(REACTIONS)}],
       now() - {self._u("g.k::text || 'rxts'")} * 60 * interval '1 day'
FROM generate_series(1, {c['reactions']}) AS g(k)
JOIN tmp_rev rv ON rv.rn = 1 + floor(power({self._u("g.k::text || 'rxp'")}, 2) * {review_total})::int
ON CONFLICT DO NOTHING
""", heavy=True)

    def _library_and_history(self):
        c = self.c
        heavy_bookmarks = min(2000, c['novels'])
        self._stage('library folders (heavy)', """
INSERT INTO lncrawler_api_libraryfolder (id, user_id, name, position, created_at)
SELECT gen_random_uuid(), 1, 'heavy-' || k, k % 10, now() FROM generate_series(1, 5) AS g(k)
""")
        self._stage('library folders', f"""
INSERT INTO lncrawler_api_libraryfolder (id, user_id, name, position, created_at)
SELECT gen_random_uuid(), {self._user_pick("g.k::text || 'fu'")}, 'folder-' || k,
       {self._h("g.k::text || 'fp'")} % 10, now() - {self._u("g.k::text || 'fts'")} * 365 * interval '1 day'
FROM generate_series(1, {c['folders']}) AS g(k)
ON CONFLICT DO NOTHING
""", heavy=True)
        self._exec("""
CREATE TEMP TABLE tmp_f1 AS
SELECT DISTINCT ON (user_id) user_id, id FROM lncrawler_api_libraryfolder ORDER BY user_id, id
""")
        self._stage('bookmarks (heavy)', f"""
INSERT INTO lncrawler_api_novelbookmark (id, user_id, novel_id, folder_id, note, position, created_at)
SELECT gen_random_uuid(), 1, {self._novel_uuid('g.n')},
       CASE WHEN g.n % 2 = 0 THEN (SELECT id FROM tmp_f1 WHERE user_id = 1) END, NULL, 0, now()
FROM generate_series(1, {heavy_bookmarks}) AS g(n)
ON CONFLICT DO NOTHING
""")
        self._stage('bookmarks', f"""
INSERT INTO lncrawler_api_novelbookmark (id, user_id, novel_id, folder_id, note, position, created_at)
SELECT gen_random_uuid(), uid.u, {self._novel_uuid(self._novel_pick("g.k::text || 'bn'"))},
       CASE WHEN {self._h("g.k::text || 'bf'")} % 2 = 0 THEN f.id END, NULL,
       {self._h("g.k::text || 'bp'")} % 20, now() - {self._u("g.k::text || 'bts'")} * 365 * interval '1 day'
FROM generate_series(1, {c['bookmarks']}) AS g(k)
CROSS JOIN LATERAL (SELECT {self._user_pick("g.k::text || 'bu'")} AS u) uid
LEFT JOIN tmp_f1 f ON f.user_id = uid.u
ON CONFLICT DO NOTHING
""", heavy=True)
        self._stage('reading history (heavy)', f"""
INSERT INTO lncrawler_api_readinghistory (id, user_id, novel_id, source_id, last_read_chapter_id, last_read_at)
SELECT gen_random_uuid(), 1, {self._novel_uuid('g.n')}, g.n, ch.id, now() - {self._u("g.n::text || 'hhts'")} * 60 * interval '1 day'
FROM generate_series(1, {heavy_bookmarks}) AS g(n)
JOIN tmp_src t ON t.source_id = g.n
LEFT JOIN lncrawler_api_chapter ch ON ch.novel_from_source_id = g.n
    AND ch.chapter_id = 1 + floor(t.cnt * power({self._u("g.n::text || 'hhc'")}, 2))::int
    AND {self._h("g.n::text || 'hhn'")} % 10 <> 0
ON CONFLICT DO NOTHING
""")
        self._stage('reading history', f"""
INSERT INTO lncrawler_api_readinghistory (id, user_id, novel_id, source_id, last_read_chapter_id, last_read_at)
SELECT gen_random_uuid(), uid.u, {self._novel_uuid("p.n")}, p.sid, ch.id,
       now() - {self._u("g.k::text || 'hts'")} * {self._u("g.k::text || 'htq'")} * 60 * interval '1 day'
FROM generate_series(1, {c['history']}) AS g(k)
CROSS JOIN LATERAL (SELECT {self._novel_pick("g.k::text || 'hn'")} AS n, {self._user_pick("g.k::text || 'hu'")} AS u) uid
JOIN tmp_first p ON p.n = uid.n
JOIN tmp_src t ON t.source_id = p.sid
LEFT JOIN lncrawler_api_chapter ch ON ch.novel_from_source_id = p.sid
    AND ch.chapter_id = 1 + floor(t.cnt * power({self._u("g.k::text || 'hc'")}, 2))::int
    AND {self._h("g.k::text || 'hn2'")} % 10 <> 0
ON CONFLICT DO NOTHING
""", heavy=True)

    def _lists_social_reader_chat(self):
        c = self.c
        self._stage('reading lists (heavy)', f"""
INSERT INTO lncrawler_api_readinglist (id, title, description, is_public, user_id, created_at, updated_at)
SELECT gen_random_uuid(), 'Heavy list ' || k, NULL, true, 1, now(), now()
FROM generate_series(1, 50) AS g(k)
""")
        self._stage('reading lists', f"""
INSERT INTO lncrawler_api_readinglist (id, title, description, is_public, user_id, created_at, updated_at)
SELECT gen_random_uuid(), 'List ' || k, NULL, {self._h("g.k::text || 'lp'")} % 5 <> 0,
       {self._user_pick("g.k::text || 'lu'")}, now() - {self._u("g.k::text || 'lts'")} * 365 * interval '1 day', now()
FROM generate_series(1, {c['reading_lists']}) AS g(k)
""", heavy=True)
        self._exec('CREATE TEMP TABLE tmp_rl AS SELECT row_number() OVER (ORDER BY id) AS rn, id FROM lncrawler_api_readinglist')
        rl_total = self._scalar('SELECT count(*) FROM tmp_rl')
        self._stage('reading list items', f"""
INSERT INTO lncrawler_api_readinglistitem (id, reading_list_id, novel_id, note, position, added_at)
SELECT gen_random_uuid(), rl.id, {self._novel_uuid(self._novel_pick("g.k::text || 'in'"))}, NULL,
       {self._h("g.k::text || 'ip'")} % 50, now() - {self._u("g.k::text || 'its'")} * 365 * interval '1 day'
FROM generate_series(1, {c['list_items']}) AS g(k)
JOIN tmp_rl rl ON rl.rn = 1 + floor(power({self._u("g.k::text || 'irl'")}, 2) * {rl_total})::int
ON CONFLICT DO NOTHING
""", heavy=True)
        self._stage('reading list collaborators', f"""
INSERT INTO lncrawler_api_readinglistcollaborator (id, reading_list_id, user_id, role, created_at)
SELECT gen_random_uuid(), rl.id, {self._user_pick("g.k::text || 'cu'")},
       CASE WHEN {self._h("g.k::text || 'cr'")} % 2 = 0 THEN 'editor' ELSE 'reader' END, now()
FROM generate_series(1, {c['list_collaborators']}) AS g(k)
JOIN tmp_rl rl ON rl.rn = 1 + {self._h("g.k::text || 'crl'")} % {rl_total}
ON CONFLICT DO NOTHING
""")
        self._stage('pinned novels', f"""
INSERT INTO lncrawler_api_profilepinnednovel (id, user_id, novel_id, position, created_at)
SELECT gen_random_uuid(), {self._user_pick("g.k::text || 'pu'")},
       {self._novel_uuid(self._novel_pick("g.k::text || 'pn'"))}, {self._h("g.k::text || 'pp'")} % 5, now()
FROM generate_series(1, {c['pinned']}) AS g(k)
ON CONFLICT DO NOTHING
""", heavy=True)
        heavy_friends = min(500, c['users'] - 1)
        self._stage('friendships (heavy)', f"""
INSERT INTO lncrawler_api_friendship (id, requester_id, addressee_id, status, created_at, updated_at)
SELECT gen_random_uuid(), 1, k + 1, 'accepted', now(), now()
FROM generate_series(1, {heavy_friends}) AS g(k)
ON CONFLICT DO NOTHING
""")
        self._stage('friendships', f"""
INSERT INTO lncrawler_api_friendship (id, requester_id, addressee_id, status, created_at, updated_at)
SELECT gen_random_uuid(), LEAST(a.u, b.u), GREATEST(a.u, b.u),
       CASE WHEN {self._h("g.k::text || 'fs'")} % 10 < 8 THEN 'accepted' ELSE 'pending' END,
       now() - {self._u("g.k::text || 'fts'")} * 365 * interval '1 day', now()
FROM generate_series(1, {c['friendships']}) AS g(k)
CROSS JOIN LATERAL (SELECT {self._user_pick("g.k::text || 'fa'")} AS u) a
CROSS JOIN LATERAL (SELECT {self._user_pick("g.k::text || 'fb'")} AS u) b
WHERE a.u <> b.u
ON CONFLICT DO NOTHING
""", heavy=True)
        self._stage('reader settings slots', f"""
INSERT INTO lncrawler_api_readersettingsslot (id, user_id, slot, data, schema_version, revision, updated_at)
SELECT gen_random_uuid(), {self._user_pick("g.k::text || 'su'")},
       CASE WHEN k % 2 = 0 THEN 'mobile' ELSE 'desktop' END, '{{}}'::jsonb, 1, 1, now()
FROM generate_series(1, {c['reader_slots']}) AS g(k)
ON CONFLICT DO NOTHING
""")
        self._stage('chat messages', f"""
INSERT INTO lncrawler_api_chatmessage (id, user_id, author_name, message, contains_spoiler, created_at,
    ip_address, edited, parent_id)
SELECT gen_random_uuid(),
       CASE WHEN {self._h("g.k::text || 'cma'")} % 10 = 0 THEN NULL ELSE {self._user_pick("g.k::text || 'cu'")} END,
       CASE WHEN {self._h("g.k::text || 'cma'")} % 10 = 0 THEN 'Anonymous'
            ELSE {self._username(self._user_pick("g.k::text || 'cu'"))} END,
       {self._words("g.k::text || 'cm'", f"5 + {self._h('g.k::text || ' + repr('cml'))} % 15")},
       false, now() - {self._u("g.k::text || 'cts'")} * 30 * interval '1 day',
       CASE WHEN {self._h("g.k::text || 'cma'")} % 10 = 0 THEN {self._ip("g.k::text || 'cip'")} END,
       false, NULL
FROM generate_series(1, {c['chat']}) AS g(k)
""", heavy=True)

    def _sql_jobs(self):
        return f"""
INSERT INTO lncrawler_api_job (id, status, job_type, query, target_url, user_id, created_at, updated_at,
    progress, total_items, progress_unit, search_results, selected_novel, output_path, output_files,
    output_slug, import_message, error_message, retry_count)
SELECT gen_random_uuid(),
       CASE WHEN {self._h("g.k::text || 'js'")} % 20 = 0 THEN 'failed' ELSE 'download_completed' END,
       CASE WHEN {self._h("g.k::text || 'jt'")} % 2 = 0 THEN 'search' ELSE 'download' END,
       'bench query ' || g.k, 'https://bench.example/job/' || g.k,
       CASE WHEN {self._h("g.k::text || 'jun'")} % 5 = 0 THEN NULL ELSE {self._user_pick("g.k::text || 'ju'")} END,
       now() - {self._u("g.k::text || 'jts'")} * 365 * interval '1 day', now(),
       100, 100, 'chapters', '{{}}'::jsonb, '{{}}'::jsonb, NULL, '[]'::jsonb, NULL, '', '', {self._h("g.k::text || 'jr'")} % 3
FROM generate_series(1, {self.c['jobs']}) AS g(k)
"""

    def _audiobooks(self):
        n_ab = self.c['audiobooks']
        self._exec(f"""
CREATE TEMP TABLE tmp_ab AS
SELECT g.k AS k, gen_random_uuid() AS abid, g.k AS n, COALESCE(en.sid, g.k) AS sid
FROM generate_series(1, {n_ab}) AS g(k)
LEFT JOIN tmp_en en ON en.n = g.k
""")
        self._stage('audiobooks', f"""
INSERT INTO lncrawler_api_audiobook (id, novel_id, language, source_id, status, published, featured, worker_id,
    cover_path, tags_hash, total_duration_s, total_size_bytes, parts_done, "cast", credits,
    first_published_at, last_part_at, last_enqueued_at, created_at, updated_at)
SELECT ab.abid, {self._novel_uuid("ab.n")}, 'en', ab.sid, 'active',
       {self._h("ab.k::text || 'pub'")} % 10 < 9, {self._h("ab.k::text || 'feat'")} % 20 = 0, '', '', '',
       0, 0, 0, '{{}}'::jsonb, '{{}}'::jsonb, now(), now(), now(), now(), now()
FROM tmp_ab ab
""")
        self._exec(f"""
CREATE TEMP TABLE tmp_parts AS
SELECT gen_random_uuid() AS id, ab.abid, ab.sid, g.k AS idx,
       floor(g.k * t.cnt / 10) + 1 AS cs, floor((g.k + 1) * t.cnt / 10) AS ce
FROM tmp_ab ab
JOIN tmp_src t ON t.source_id = ab.sid
CROSS JOIN generate_series(0, 9) AS g(k)
""")
        self._stage('audiobook parts', f"""
INSERT INTO lncrawler_api_audiobookpart (id, audiobook_id, "index", chapter_start, chapter_end, word_count,
    estimated_duration_s, status, priority, engine, engine_version, worker_id, progress, stage, attempts,
    error_message, content_hash, chapter_ids, generation, uploads, "cast", qa, qa_passed, approved, duration_s,
    size_bytes, created_at, completed_at, checked_at)
SELECT p.id, p.abid, p.idx, p.cs, p.ce, 0, 600, 'done', 0, 'bench', '1', '', 1.0, 'done', 1,
       '', md5(p.id::text), '[]'::jsonb, 1, '{{}}'::jsonb, '{{}}'::jsonb, '{{}}'::jsonb, true, true,
       600 + {self._h("p.id::text || 'dur'")} % 1200, 9600000, now(), now(), now()
FROM tmp_parts p
""")
        self._stage('audiobook chapters', f"""
INSERT INTO lncrawler_api_audiobookchapter (part_id, chapter_id, file_path, duration_s, size_bytes, sha256, offset_s)
SELECT p.id, ch.id, 'audio/bench/' || p.abid::text || '/' || ch.chapter_id || '.ogg',
       5 + {self._h("ch.id::text || 'ad'")} % 60, 80000 + {self._h("ch.id::text || 'as'")} % 40000,
       encode(sha256(convert_to(ch.id::text, 'UTF8')), 'hex'), 0
FROM tmp_parts p
JOIN lncrawler_api_chapter ch ON ch.novel_from_source_id = p.sid AND ch.chapter_id BETWEEN p.cs AND p.ce
""", heavy=True)
        self._stage('listening progress', f"""
INSERT INTO lncrawler_api_listeningprogress (user_id, audiobook_id, chapter_id, position_s, speed, finished, updated_at)
SELECT {self._user_pick("g.k::text || 'lpu'")}, ab.abid, ch.id, {self._u("g.k::text || 'lpp'")} * 3600, 1.0,
       {self._h("g.k::text || 'lpf'")} % 10 = 0, now()
FROM generate_series(1, {self.c['listening']}) AS g(k)
JOIN tmp_ab ab ON ab.k = 1 + floor({self._u("g.k::text || 'lpa'")} * {n_ab})::int
JOIN tmp_src t ON t.source_id = ab.sid
LEFT JOIN lncrawler_api_chapter ch ON ch.novel_from_source_id = ab.sid
    AND ch.chapter_id = 1 + floor(t.cnt * {self._u("g.k::text || 'lpc'")})::int
ON CONFLICT DO NOTHING
""")
        self._stage('audiobook daily stats', """
INSERT INTO lncrawler_api_audiobookdailystat (audiobook_id, date, plays, downloads, listen_seconds)
SELECT ab.abid, current_date - d, 1 + (ab.k * 7 + d * 13) % 200, (ab.k + d) % 20, (ab.k * 31 + d * 17) % 5000
FROM tmp_ab ab
CROSS JOIN generate_series(0, 29) AS g(d)
ON CONFLICT DO NOTHING
""")
        for ab in Audiobook.objects.all():
            ab.refresh_totals()

    # ----- files, denormalised fields, summary ------------------------------

    def _write_files(self):
        base = os.path.join(settings.LNCRAWL_OUTPUT_PATH, SOURCE_PATH, 'json')
        os.makedirs(base, exist_ok=True)
        started = time.perf_counter()
        written = 0
        for number in range(1, FILE_COUNT + 1):
            path = os.path.join(base, f'{number:05}.json')
            if os.path.exists(path):
                continue
            rng = random.Random(f'{self.seed}-{number}')
            paragraphs = []
            words_total = 0
            while words_total < 2500:
                size = rng.randint(60, 110)
                sentence_words = [rng.choice(VOCAB) for _ in range(size)]
                sentence_words[0] = sentence_words[0].capitalize()
                paragraphs.append('<p>' + ' '.join(sentence_words) + '.</p>')
                words_total += size
            title = f'Chapter {number}'
            payload = {
                'id': str(number),
                'url': f'https://bench-source-01.example/bench/chapter-{number}',
                'title': title,
                'volume': str((number - 1) // 100),
                'volume_title': f'Volume {(number - 1) // 100 + 1}',
                'body': f'<h1>{title}</h1>' + ''.join(paragraphs),
                'images': '{}',
                'success': 'True',
                'source_version': '2',
                'word_count': str(words_total),
            }
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh)
            written += 1
        self.timings.append(('chapter files', written, time.perf_counter() - started))
        self.stdout.write(
            f'{"chapter files":<28} {written:>13,} written in {time.perf_counter() - started:.1f}s to {base}'
        )

    def _finish(self, name, total_seconds):
        self.stdout.write('Denormalised fields')
        self._exec("""
UPDATE lncrawler_api_novel n SET comment_count = x.cnt
FROM (
    SELECT novel_id, sum(cnt) AS cnt FROM (
        SELECT novel_id, count(*) AS cnt FROM lncrawler_api_comment WHERE novel_id IS NOT NULL GROUP BY novel_id
        UNION ALL
        SELECT s.novel_id, count(*) FROM lncrawler_api_comment c
        JOIN lncrawler_api_chapter ch ON ch.id = c.chapter_id
        JOIN lncrawler_api_novelfromsource s ON s.id = ch.novel_from_source_id
        GROUP BY s.novel_id
    ) parts GROUP BY novel_id
) x
WHERE n.id = x.novel_id
""")
        self._exec("""
UPDATE lncrawler_api_novelfromsource s
SET total_views = x.total
FROM (SELECT source_id, sum(views) AS total FROM lncrawler_api_weeklysourceview GROUP BY source_id) x
WHERE s.id = x.source_id
""")
        self._exec("""
UPDATE lncrawler_api_novelfromsource s
SET is_adult = s.adult_from_source OR EXISTS (
    SELECT 1 FROM lncrawler_api_novelfromsource_tags st
    JOIN lncrawler_api_tag t ON t.id = st.tag_id
    WHERE st.novelfromsource_id = s.id AND t.is_adult)
""")
        self.stdout.write(f'Novel rankings: {refresh_novel_rankings()} rows updated')
        self.stdout.write(f'Chapter stats: {refresh_chapter_stats()} rows updated')

        self.stdout.write('Analyzing ...')
        started = time.perf_counter()
        with connection.cursor() as cur:
            cur.execute('VACUUM ANALYZE')
        self.timings.append(('vacuum analyze', 0, time.perf_counter() - started))

        self.stdout.write('')
        self.stdout.write(f"{'table':<40} {'rows':>14}")
        self.stdout.write('-' * 56)
        for table in self._summary_tables():
            count = self._scalar(f'SELECT count(*) FROM {table}')
            self.stdout.write(f'{table:<40} {count:>14,}')
        size = self._scalar('SELECT pg_size_pretty(pg_database_size(current_database()))')
        self.stdout.write('-' * 56)
        self.stdout.write(f'{name} size: {size}')
        self.stdout.write(f'Total time: {total_seconds:.1f}s')
        self.stdout.write(self.style.SUCCESS('seed_bench finished'))

    def _summary_tables(self):
        return [
            'auth_app_customuser', 'lncrawler_api_novel', 'lncrawler_api_novelfromsource',
            'lncrawler_api_volume', 'lncrawler_api_chapter', 'lncrawler_api_tag',
            'lncrawler_api_author', 'lncrawler_api_novelrating', 'lncrawler_api_review',
            'lncrawler_api_comment', 'lncrawler_api_commentvote', 'lncrawler_api_sourcevote',
            'lncrawler_api_novelbookmark', 'lncrawler_api_readinghistory', 'lncrawler_api_readinglist',
            'lncrawler_api_readinglistitem', 'lncrawler_api_friendship', 'lncrawler_api_weeklysourceview',
            'lncrawler_api_novelsimilarity', 'lncrawler_api_job', 'lncrawler_api_audiobook',
            'lncrawler_api_audiobookpart', 'lncrawler_api_audiobookchapter',
        ]
