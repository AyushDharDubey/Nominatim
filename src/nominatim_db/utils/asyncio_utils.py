# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Nominatim. (https://nominatim.org)
#
# Copyright (C) 2026 by the Nominatim developer community.
# For a full list of authors see the git log.
"""
Helper functions to get appropriate asyncio loop factory based on platform.
"""
import sys
import asyncio
import selectors
from typing import Callable, Optional


def get_loop_factory() -> Optional[Callable[[], asyncio.AbstractEventLoop]]:
    """Returns a compatible loop factory for Python 3.12+ on Windows,
    or None for Unix based systems."""

    if sys.version_info >= (3, 12) and sys.platform == "win32":
        return lambda: asyncio.SelectorEventLoop(selectors.DefaultSelector())
    return None
