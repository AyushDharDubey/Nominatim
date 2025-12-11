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
  search_tokens INTEGER[];

BEGIN
  -- extract tokens
  in_token_info := COALESCE(in_token_info, '[]'::jsonb);

-- Convert JSONB array to PostgreSQL Integer Array
  SELECT ARRAY(
      SELECT jsonb_array_elements_text(
          CASE WHEN jsonb_typeof(in_token_info) = 'array' THEN in_token_info
          ELSE '[]'::jsonb END -- if NULL
      )::int
  ) INTO search_tokens;

  IF array_length(search_tokens, 1) IS NULL THEN
    RETURN NULL;
  END IF;


  SELECT place_id INTO out_place_id 
    FROM search_name
    WHERE 
        -- finds rows where name_vector shares elements with search tokens.
        name_vector && search_tokens
        -- limits search area
        AND centroid && ST_Expand(in_centroid, 0.015) 
        AND address_rank BETWEEN 26 AND 27
    ORDER BY ST_Distance(centroid, in_centroid) ASC 
    LIMIT 1;

  RETURN out_place_id;
END;
$$
LANGUAGE plpgsql;
