# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Nominatim. (https://nominatim.org)
#
# Copyright (C) 2026 by the Nominatim developer community.
# For a full list of authors see the git log.
"""
Sanitizer that removes name tags which are a simple concatenation of
language-specific name tags.

In areas where multiple languages are spoken, OSM often has a `name` tag
which contains all language variants joined by a delimiter (e.g.
``name=Rue du Marché aux Poulets - Kiekenmarkt``). These language variants
also appear in separate tags like ``name:fr`` and ``name:nl``. The
combined name is redundant and adds noise to the search index.

This sanitizer detects when a bare ``name`` tag (i.e. one without a
language suffix) consists entirely of a concatenation of names that are
already present in language-specific name tags, and removes it.

Arguments:
    delimiters: A list of delimiter strings to try when checking if the
                name is a concatenation.
                (default: ``["/", "-", ";", " "]``)

    filter-kind: Define which 'kind' of names are considered for
                 removal. Takes a string or list of strings where each
                 string is a regular expression.
                 (default: ``name``)
"""
from typing import Sequence

from .base import ProcessInfo, SanitizerFunc
from .config import SanitizerConfig


def create(config: SanitizerConfig) -> SanitizerFunc:
    """ Create a function to remove multilingual concatenated names.
    """
    delimiters: Sequence[str] = config.get_string_list('delimiters',
                                                       ['/', '-', ';', ' '])
    filter_kind = config.get_filter('filter-kind', ['name'])

    def _is_concatenated(name_value: str, lang_names: set[str]) -> bool:
        """ Check if name_value is a concatenation of values from lang_names
            joined by one of the configured delimiters.
        """
        if len(lang_names) < 2:
            return False

        for delimiter in delimiters:
            parts = name_value.split(delimiter)
            if len(parts) >= 2 and all(p.strip() in lang_names for p in parts):
                return True

        return False

    def _process(obj: ProcessInfo) -> None:
        if not obj.names:
            return

        # Collect language-specific name values for each kind.
        # A language-specific name has the same kind but a non-empty suffix.
        lang_names_by_kind: dict[str, set[str]] = {}
        for name in obj.names:
            if name.suffix and filter_kind(name.kind):
                lang_names_by_kind.setdefault(name.kind, set()).add(name.name)

        if not lang_names_by_kind:
            return

        new_names = []
        for name in obj.names:
            if name.suffix is None \
               and filter_kind(name.kind) \
               and name.kind in lang_names_by_kind \
               and _is_concatenated(name.name, lang_names_by_kind[name.kind]):
                continue  # Skip this redundant concatenated name
            new_names.append(name)

        obj.names = new_names

    return _process
