# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Nominatim. (https://nominatim.org)
#
# Copyright (C) 2026 by the Nominatim developer community.
# For a full list of authors see the git log.
"""
Tests for the sanitizer that removes multilingual concatenated names.
"""
import pytest

from nominatim_db.config import Configuration
from nominatim_db.data.place_info import PlaceInfo
from nominatim_db.tokenizer.place_sanitizer import PlaceSanitizer


@pytest.fixture
def run_sanitizer(def_config):
    def _run(extra_args=None, **kwargs):
        place = PlaceInfo({'name': {k.replace('_', ':'): v
                                    for k, v in kwargs.items()},
                           'country_code': 'be', 'rank_address': 26})

        sanitizer_args = {'step': 'clean-multilingual-names'}
        if extra_args:
            sanitizer_args.update(extra_args)

        PlaceSanitizer([sanitizer_args], def_config).process_names(place)

        return sorted([(p.name, p.kind, p.suffix or '')
                       for p in place.searchable_names])

    return _run


class TestDelimiter:
    """Test removal with some common delimiters used worlwide."""

    def test_hyphen_delimiter(self, run_sanitizer):
        res = run_sanitizer(name='गढ़वा - Garhwa-گڑھوا',
                            name_hi='गढ़वा',
                            name_en='Garhwa',
                            name_ur='گڑھوا')

        assert ('गढ़वा - Garhwa-گڑھوا', 'name', '') not in res
        assert ('गढ़वा', 'name', 'hi') in res
        assert ('Garhwa', 'name', 'en') in res
        assert ('گڑھوا', 'name', 'ur') in res

    def test_slash_delimiter(self, run_sanitizer):
        res = run_sanitizer(name='Rue de la Gare / Stationsstraat/Bahnhofstraße',
                            name_fr='Rue de la Gare',
                            name_nl='Stationsstraat',
                            name_de='Bahnhofstraße')

        assert ('Rue de la Gare / Stationsstraat/Bahnhofstraße', 'name', '') not in res
        assert ('Rue de la Gare', 'name', 'fr') in res
        assert ('Stationsstraat', 'name', 'nl') in res
        assert ('Bahnhofstraße', 'name', 'de') in res

    def test_semicolon_no_spaces(self, run_sanitizer):
        res = run_sanitizer(name='Helsinki;Helsingfors',
                            name_fi='Helsinki',
                            name_sv='Helsingfors')

        assert ('Helsinki;Helsingfors', 'name', '') not in res
        assert ('Helsinki', 'name', 'fi') in res
        assert ('Helsingfors', 'name', 'sv') in res

    def test_semicolon_with_spaces(self, run_sanitizer):
        res = run_sanitizer(name='Helsinki ; Helsingfors; हेलसिंकी',
                            name_fi='Helsinki',
                            name_sv='Helsingfors',
                            name_hi='हेलसिंकी')

        assert ('Helsinki ; Helsingfors; हेलसिंकी', 'name', '') not in res
        assert ('Helsinki', 'name', 'fi') in res
        assert ('Helsingfors', 'name', 'sv') in res
        assert ('हेलसिंकी', 'name', 'hi') in res

    def test_extra_whitespace_in_parts(self, run_sanitizer):
        """Parts with leading/trailing whitespace after splitting should
        be stripped before comparison."""
        res = run_sanitizer(name='गढ़वा ;    Garhwa',
                            name_fr='गढ़वा',
                            name_nl='Garhwa')

        assert ('गढ़वा ;    Garhwa', 'name', '') not in res
        assert ('गढ़वा', 'name', 'fr') in res
        assert ('Garhwa', 'name', 'nl') in res

    def test_space_delimiter(self, run_sanitizer):
        res = run_sanitizer(name='गढ़वा Garhwa',
                            name_fr='गढ़वा',
                            name_nl='Garhwa')

        assert ('गढ़वा Garhwa', 'name', '') not in res

    def test_space_delimiter_normal_multiword_name_kept(self, run_sanitizer):
        """A normal multi-word name should NOT be split and removed if its parts
        don't exactly match the language-specific names."""
        res = run_sanitizer(name='New York City',
                            name_en='New York City',
                            name_fr='Ville de New York')

        assert ('New York City', 'name', '') in res

    def test_name_does_not_match_any_pattern(self, run_sanitizer):
        res = run_sanitizer(name='Some Unique Name',
                            name_fr='Rue du Poulet',
                            name_nl='Kiekenstraat')

        assert ('Some Unique Name', 'name', '') in res

    def test_partial_match(self, run_sanitizer):
        res = run_sanitizer(name='Rue du Poulet - Unknown',
                            name_fr='Rue du Poulet',
                            name_nl='Kiekenstraat')

        assert ('Rue du Poulet - Unknown', 'name', '') in res

    def test_single_language_tag_exact_match(self, run_sanitizer):
        """A name identical to the only language tag is not a concatenation of
        multilingual parts."""
        res = run_sanitizer(name='गढ़वा', name_en='गढ़वा')

        assert ('गढ़वा', 'name', '') in res

    def test_custom_delimiter(self, run_sanitizer):
        res = run_sanitizer(extra_args={'delimiters': ['|']},
                            name='गढ़वा|Garhwa',
                            name_fr='गढ़वा',
                            name_nl='Garhwa')

        assert ('गढ़वा|Garhwa', 'name', '') not in res


class TestFilterKind:
    """Test with custom filter-kind configuration."""

    def test_filter_kind_ref(self, run_sanitizer):
        """When filter-kind is set to 'ref', only ref names are processed."""
        place = PlaceInfo({'name': {'name': 'गढ़वा - Garhwa',
                                    'name:fr': 'गढ़वा',
                                    'name:nl': 'Garhwa',
                                    'ref': 'A - B',
                                    'ref:fr': 'A',
                                    'ref:nl': 'B'},
                           'country_code': 'be', 'rank_address': 26})

        cfg = Configuration(None)
        PlaceSanitizer([{'step': 'clean-multilingual-names',
                         'filter-kind': 'ref'}], cfg).process_names(place)

        names = [(p.name, p.kind, p.suffix or '') for p in place.searchable_names]
        # 'name' bare tag should be kept (not matched by filter-kind)
        assert ('गढ़वा - Garhwa', 'name', '') in names
        # 'ref' bare tag should be removed
        assert ('A - B', 'ref', '') not in names

    def test_alt_name_not_affected_by_default(self, run_sanitizer):
        """alt_name has kind='alt_name', which doesn't match default
        filter-kind='name'."""
        place = PlaceInfo({'name': {'name': 'गढ़वा - Garhwa',
                                    'name:fr': 'गढ़वा',
                                    'name:nl': 'Garhwa',
                                    'alt_name': 'Baz - Qux',
                                    'alt_name:fr': 'Baz',
                                    'alt_name:nl': 'Qux'},
                           'country_code': 'be', 'rank_address': 26})

        cfg = Configuration(None)
        PlaceSanitizer([{'step': 'clean-multilingual-names'}], cfg).process_names(place)

        names = [(p.name, p.kind, p.suffix or '') for p in place.searchable_names]
        assert ('गढ़वा - Garhwa', 'name', '') not in names
        assert ('गढ़वा', 'name', 'fr') in names
        assert ('Garhwa', 'name', 'nl') in names
        assert ('Baz - Qux', 'alt_name', '') in names
        assert ('Baz', 'alt_name', 'fr') in names
        assert ('Qux', 'alt_name', 'nl') in names
