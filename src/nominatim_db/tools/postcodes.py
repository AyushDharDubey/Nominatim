# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Nominatim. (https://nominatim.org)
#
# Copyright (C) 2025 by the Nominatim developer community.
# For a full list of authors see the git log.
"""
Functions for importing, updating and otherwise maintaining the table
of artificial postcode centroids.
"""
from typing import Optional, Tuple, Dict, TextIO, Any
from collections import defaultdict
from pathlib import Path
import csv
import gzip
import logging
import json
from math import isfinite

from psycopg import sql as pysql

from ..db.connection import connect, Connection, table_exists
from ..utils.centroid import PointsCentroid
from ..data.postcode_format import PostcodeFormatter, CountryPostcodeMatcher
from ..tokenizer.base import AbstractAnalyzer, AbstractTokenizer

LOG = logging.getLogger()


def _to_float(numstr: str | float, max_value: float) -> float:
    """ Convert the number in string into a float. The number is expected
        to be in the range of [-max_value, max_value]. Otherwise rises a
        ValueError.
    """
    num = float(numstr)
    if not isfinite(num) or num <= -max_value or num >= max_value:
        raise ValueError()

    return num


def _extent_to_rank(extent: int) -> int:
    """ Guess a suitable search rank from the extent of a postcode.
    """
    if extent <= 100:
        return 25
    if extent <= 3000:
        return 23
    return 21


class _PostcodeCollector:
    """ Collector for postcodes of a single country.
    """

    def __init__(self, country: str, matcher: Optional[CountryPostcodeMatcher],
                 default_extent: int, exclude: set[str] = set()):
        self.country = country
        self.matcher = matcher
        self.default_extent = default_extent
        self.exclude = exclude
        self.collected: Dict[str, PointsCentroid] = defaultdict(PointsCentroid)
        self.extents: Dict[str, int] = {}
        self.geometries: Dict[str, str] = {}
        self.normalization_cache: Optional[Tuple[str, Optional[str]]] = None

    def add(self, postcode: str, x: Optional[float], y: Optional[float],
            extent: Optional[int] = None, geometry: Optional[str] = None,
            is_external: bool = False) -> None:
        """ Add the given postcode to the collection cache. If the postcode
            already existed, it is overwritten with the new centroid.
        """
        if self.matcher is not None:
            normalized: Optional[str]
            if self.normalization_cache and self.normalization_cache[0] == postcode:
                normalized = self.normalization_cache[1]
            else:
                match = self.matcher.match(postcode)
                normalized = self.matcher.normalize(match) if match else None
                self.normalization_cache = (postcode, normalized)

            if normalized and normalized not in self.exclude:
                if is_external:
                    if normalized not in self.collected:
                        if x is not None and y is not None:
                            self.collected[normalized] += (x, y)
                        else:
                            # Touch the collector to ensure the postcode is recorded
                            self.collected[normalized]
                    if extent is not None:
                        self.extents[normalized] = extent
                    if geometry is not None:
                        self.geometries[normalized] = geometry
                else:
                    assert x is not None and y is not None
                    self.collected[normalized] += (x, y)

    def commit(self, conn: Connection, analyzer: AbstractAnalyzer,
               project_dir: Optional[Path], is_initial: bool) -> None:
        """ Update postcodes for the country from the postcodes selected so far.

            When 'project_dir' is set, then any postcode files found in this
            directory are taken into account as well.
        """
        if project_dir is not None:
            self._update_from_external(analyzer, project_dir)

        if is_initial:
            to_delete = []
        else:
            with conn.cursor() as cur:
                cur.execute("""SELECT postcode FROM location_postcodes
                               WHERE country_code = %s AND osm_id is null""",
                            (self.country, ))
                to_delete = [row[0] for row in cur if row[0] not in self.collected]

        to_add = []
        for k, v in self.collected.items():
            extent = self.extents.get(k, self.default_extent)
            try:
                x, y = v.centroid()
            except ValueError:
                x, y = None, None

            geom = self.geometries.get(k)
            if x is None and geom is None:
                continue

            to_add.append({'pc': k, 'x': x, 'y': y,
                           'rank': _extent_to_rank(extent),
                           'geom': geom,
                           'extent': extent})

        self.collected = defaultdict(PointsCentroid)
        self.extents = {}
        self.geometries = {}

        LOG.info("Processing country '%s' (%s added, %s deleted).",
                 self.country, len(to_add), len(to_delete))

        with conn.cursor() as cur:
            if to_add:
                columns = ['country_code',
                           'rank_search',
                           'postcode',
                           'centroid',
                           'geometry']
                values = [pysql.Literal(self.country),
                          pysql.Placeholder('rank'),
                          pysql.Placeholder('pc'),
                          pysql.SQL("""COALESCE(ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 4326),
                                                ST_Centroid(ST_GeomFromGeoJSON(%(geom)s)))"""),
                          pysql.SQL("""COALESCE(ST_GeomFromGeoJSON(%(geom)s),
                                                expand_by_meters(ST_SetSRID(
                                                ST_MakePoint(%(x)s, %(y)s), 4326), %(extent)s))""")]
                if is_initial:
                    columns.extend(('place_id', 'indexed_status'))
                    values.extend((pysql.SQL("nextval('seq_place')"), pysql.Literal(1)))

                cur.executemany(pysql.SQL("INSERT INTO location_postcodes ({}) VALUES ({})")
                                     .format(pysql.SQL(',')
                                                  .join(pysql.Identifier(c) for c in columns),
                                             pysql.SQL(',').join(values)),
                                to_add)
            if to_delete:
                cur.execute("""DELETE FROM location_postcodes
                               WHERE country_code = %s and postcode = any(%s)
                                     AND osm_id is null
                            """, (self.country, to_delete))

    def _update_from_external(self, analyzer: AbstractAnalyzer, project_dir: Path) -> None:
        """ Look for an external postcode file for the active country in
            the project directory and add missing postcodes when found.
            Prioritises jsonl files over csv and gzipped files over
            uncompressed ones.
        """
        for ext in ('.jsonl', '.jsonl.gz', '.csv', '.csv.gz'):
            fname = project_dir / f'{self.country}_postcodes{ext}'
            if fname.is_file():
                LOG.info("Using external postcode file '%s'.", fname)
                fh: Any
                if ext.endswith('.gz'):
                    fh = gzip.open(fname, 'rt', encoding='utf-8')
                else:
                    fh = open(fname, 'r', encoding='utf-8')

                try:
                    if '.jsonl' in ext:
                        self._read_external_jsonl(analyzer, fh)
                    else:
                        self._read_external_csv(analyzer, fh)
                finally:
                    fh.close()
                return

    def _read_external_csv(self, analyzer: AbstractAnalyzer, fh: TextIO) -> None:
        reader = csv.DictReader(fh)
        for row in reader:
            if 'postcode' not in row or 'lat' not in row or 'lon' not in row:
                LOG.warning("Bad format for external postcode file for country '%s'."
                            " Ignored.", self.country)
                return
            postcode = analyzer.normalize_postcode(row['postcode'])
            if postcode not in self.collected:
                try:
                    # Do float conversation separately, it might throw
                    x = _to_float(row['lon'], 180)
                    y = _to_float(row['lat'], 90)
                    self.add(postcode, x, y, is_external=True)
                except ValueError:
                    LOG.warning("Bad coordinates %s, %s in '%s' country postcode file.",
                                row['lat'], row['lon'], self.country)

    def _read_external_jsonl(self, analyzer: AbstractAnalyzer, fh: TextIO) -> None:
        for i, line in enumerate(fh, start=1):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                LOG.warning("Not a valid JSON line in line no %s. Ignored.", i)
                continue

            props = data.get('properties', {})
            postcode = postcode = analyzer.normalize_postcode(props.get('postcode'))
            extent = props.get('extent')
            geometry = data.get('geometry')

            if not postcode:
                LOG.warning("Missing postcode in line %s for country '%s'. Ignored.",
                            i, self.country)
                continue

            lon = props.get('lon')
            lat = props.get('lat')
            if lon is not None and lat is not None:
                try:
                    lon = _to_float(lon, 180)
                    lat = _to_float(lat, 90)
                except ValueError:
                    LOG.warning("Bad centroid coordinates %s, %s in '%s' country postcode file.",
                                lat, lon, self.country)
            elif geometry is None:
                LOG.warning("No centroid or geometry found for postcode '%s' in line %s of country"
                            " '%s' postcode file. Ignored.", postcode, i, self.country)
                continue

            geom_json = json.dumps(geometry) if geometry else None

            if postcode not in self.collected:
                try:
                    self.add(postcode, lon, lat,
                             extent=int(extent) if extent is not None else None,
                             geometry=geom_json, is_external=True)
                except (ValueError, TypeError):
                    LOG.warning("Bad GeoJSON object in line %s of country '%s' postcode file.",
                                i, self.country)


def update_postcodes(dsn: str, project_dir: Optional[Path],
                     tokenizer: AbstractTokenizer, force_reimport: bool = False) -> None:
    """ Update the table of postcodes from the input tables
        placex and place_postcode.
    """
    matcher = PostcodeFormatter()
    with tokenizer.name_analyzer() as analyzer:
        with connect(dsn) as conn:
            # Backfill country_code column where required
            conn.execute("""UPDATE place_postcode
                              SET country_code = get_country_code(centroid)
                              WHERE country_code is null
                         """)
            if force_reimport:
                conn.execute("TRUNCATE location_postcodes")
                is_initial = True
            else:
                is_initial = _is_postcode_table_empty(conn)
            if is_initial:
                conn.execute("""ALTER TABLE location_postcodes
                                DISABLE TRIGGER location_postcodes_before_insert""")
            # Now update first postcode areas
            _update_postcode_areas(conn, analyzer, matcher, is_initial)
            # Then fill with estimated postcode centroids from other info
            _update_guessed_postcode(conn, analyzer, matcher, project_dir, is_initial)
            if is_initial:
                conn.execute("""ALTER TABLE location_postcodes
                                ENABLE TRIGGER location_postcodes_before_insert""")
            conn.commit()

        analyzer.update_postcodes_from_db()


def _is_postcode_table_empty(conn: Connection) -> bool:
    """ Check if there are any entries in the location_postcodes table yet.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT place_id FROM location_postcodes LIMIT 1")
        return cur.fetchone() is None


def _insert_postcode_areas(conn: Connection, country_code: str,
                           extent: int, pcs: list[dict[str, str]],
                           is_initial: bool) -> None:
    if pcs:
        with conn.cursor() as cur:
            columns = ['osm_id', 'country_code',
                       'rank_search', 'postcode',
                       'centroid', 'geometry']
            values = [pysql.Identifier('osm_id'), pysql.Identifier('country_code'),
                      pysql.Literal(_extent_to_rank(extent)), pysql.Placeholder('out'),
                      pysql.Identifier('centroid'), pysql.Identifier('geometry')]
            if is_initial:
                columns.extend(('place_id', 'indexed_status'))
                values.extend((pysql.SQL("nextval('seq_place')"), pysql.Literal(1)))

            cur.executemany(
                pysql.SQL(
                    """ INSERT INTO location_postcodes ({})
                            SELECT {} FROM place_postcode
                            WHERE osm_type = 'R'
                                  and country_code = {} and postcode = %(in)s
                                  and geometry is not null
                    """).format(pysql.SQL(',')
                                     .join(pysql.Identifier(c) for c in columns),
                                pysql.SQL(',').join(values),
                                pysql.Literal(country_code)),
                pcs)


def _update_postcode_areas(conn: Connection, analyzer: AbstractAnalyzer,
                           matcher: PostcodeFormatter, is_initial: bool) -> None:
    """ Update the postcode areas made from postcode boundaries.
    """
    # first delete all areas that have gone
    if not is_initial:
        conn.execute(""" DELETE FROM location_postcodes pc
                         WHERE pc.osm_id is not null
                           AND NOT EXISTS(
                                  SELECT * FROM place_postcode pp
                                  WHERE pp.osm_type = 'R' and pp.osm_id = pc.osm_id
                                        and geometry is not null)
                    """)
    # now insert all in country batches, triggers will ensure proper updates
    with conn.cursor() as cur:
        cur.execute(""" SELECT country_code, postcode FROM place_postcode
                        WHERE geometry is not null and osm_type = 'R'
                        ORDER BY country_code
                    """)
        country_code = None
        fmt = None
        pcs = []
        for cc, postcode in cur:
            if country_code is None:
                country_code = cc
                fmt = matcher.get_matcher(country_code)
            elif country_code != cc:
                _insert_postcode_areas(conn, country_code,
                                       matcher.get_postcode_extent(country_code), pcs,
                                       is_initial)
                country_code = cc
                fmt = matcher.get_matcher(country_code)
                pcs = []

            if fmt is not None:
                if (m := fmt.match(postcode)):
                    pcs.append({'out': fmt.normalize(m), 'in': postcode})

        if country_code is not None and pcs:
            _insert_postcode_areas(conn, country_code,
                                   matcher.get_postcode_extent(country_code), pcs,
                                   is_initial)


def _update_guessed_postcode(conn: Connection, analyzer: AbstractAnalyzer,
                             matcher: PostcodeFormatter, project_dir: Optional[Path],
                             is_initial: bool) -> None:
    """ Computes artificial postcode centroids from the placex table,
        potentially enhances it with external data and then updates the
        postcodes in the table 'location_postcodes'.
    """
    # First get the list of countries that currently have postcodes.
    # (Doing this before starting to insert, so it is fast on import.)
    if is_initial:
        todo_countries: set[str] = set()
    else:
        with conn.cursor() as cur:
            cur.execute("""SELECT DISTINCT country_code FROM location_postcodes
                            WHERE osm_id is null""")
            todo_countries = {row[0] for row in cur}

    # Next, get the list of postcodes that are already covered by areas.
    area_pcs = defaultdict(set)
    with conn.cursor() as cur:
        cur.execute("""SELECT country_code, postcode
                       FROM location_postcodes WHERE osm_id is not null
                       ORDER BY country_code""")
        for cc, pc in cur:
            area_pcs[cc].add(pc)

    # Create a temporary table which contains coverage of the postcode areas.
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS _global_postcode_area")
        cur.execute("""CREATE TABLE _global_postcode_area AS
                       (SELECT ST_SubDivide(ST_SimplifyPreserveTopology(
                                              ST_Union(geometry), 0.00001), 128) as geometry
                        FROM place_postcode WHERE geometry is not null)
                    """)
        cur.execute("CREATE INDEX ON _global_postcode_area USING gist(geometry)")

    # Recompute the list of valid postcodes from placex.
    with conn.cursor(name="placex_postcodes") as cur:
        cur.execute("""
            SELECT country_code, postcode, ST_X(centroid), ST_Y(centroid)
              FROM (
                (SELECT country_code, address->'postcode' as postcode, centroid
                  FROM placex WHERE address ? 'postcode')
                UNION
                (SELECT country_code, postcode, centroid
                 FROM place_postcode WHERE geometry is null)
              ) x
              WHERE not postcode like '%,%' and not postcode like '%;%'
                    AND NOT EXISTS(SELECT * FROM _global_postcode_area g
                                   WHERE ST_Intersects(x.centroid, g.geometry))
              ORDER BY country_code""")

        collector = None

        for country, postcode, x, y in cur:
            if collector is None or country != collector.country:
                if collector is not None:
                    collector.commit(conn, analyzer, project_dir, is_initial)
                collector = _PostcodeCollector(country, matcher.get_matcher(country),
                                               matcher.get_postcode_extent(country),
                                               exclude=area_pcs[country])
                todo_countries.discard(country)
            collector.add(postcode, x, y)

        if collector is not None:
            collector.commit(conn, analyzer, project_dir, is_initial)

    # Now handle any countries that are only in the postcode table.
    for country in todo_countries:
        fmt = matcher.get_matcher(country)
        ext = matcher.get_postcode_extent(country)
        _PostcodeCollector(country, fmt, ext,
                           exclude=area_pcs[country]).commit(conn, analyzer, project_dir, False)

    conn.execute("DROP TABLE IF EXISTS _global_postcode_area")


def can_compute(dsn: str) -> bool:
    """ Check that the necessary tables exist so that postcodes can be computed.
    """
    with connect(dsn) as conn:
        return table_exists(conn, 'place_postcode')
