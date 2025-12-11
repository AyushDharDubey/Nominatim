-- SPDX-License-Identifier: GPL-2.0-only
--
-- This file is part of Nominatim. (https://nominatim.org)
--
-- Copyright (C) 2022 by the Nominatim developer community.
-- For a full list of authors see the git log.

-- Lookup functions for tiger import when update 
-- informations are dropped (see gh-issue #2463)


CREATE OR REPLACE FUNCTION lookup_road_in_search_name(
    in_centroid GEOMETRY, 
    in_token_info JSONB)
  RETURNS BIGINT
  AS $$
DECLARE
  out_place_id BIGINT;

BEGIN
  SELECT place_id INTO out_place_id 
      FROM search_name
    WHERE token_matches_street(in_token_info, name_vector)
      AND centroid && ST_Expand(in_centroid, 0.015)
      AND address_rank between 26 and 27
    ORDER BY ST_Distance(centroid, in_centroid) ASC limit 1;

  RETURN out_place_id;
END;
$$
LANGUAGE plpgsql;
