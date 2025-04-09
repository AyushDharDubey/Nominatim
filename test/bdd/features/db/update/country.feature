Feature: Country handling
    Tests for update of country information

    Background:
        Given the 1.0 grid with origin DE
            | 1 |    | 2 |
            |   | 10 |   |
            | 4 |    | 3 |

    Scenario: When country names are changed old ones are no longer searchable
        Given the places
            | osm | class    | type           | admin | name+name:xy | country | geometry |
            | R1  | boundary | administrative | 2     | Loudou       | de      | (1,2,3,4,1) |
        Given the places
            | osm | class    | type          | name  |
            | N10 | place    | town          | Wenig |
        When importing
        When geocoding "Wenig, Loudou"
        Then all results contain
            | object |
            | N10 |
        When updating places
            | osm | class    | type           | admin | name+name:xy | country | geometry |
            | R1  | boundary | administrative | 2     | Germany      | de      | (1,2,3,4,1) |
        When geocoding "Wenig, Loudou"
        Then exactly 0 results are returned

    Scenario: When country names are deleted they are no longer searchable
        Given the places
            | osm | class    | type           | admin | name+name:xy | country | geometry |
            | R1  | boundary | administrative | 2     | Loudou       | de      | (1,2,3,4,1) |
        Given the places
            | osm | class    | type          | name  |
            | N10 | place    | town          | Wenig |
        When importing
        When geocoding "Wenig, Loudou"
        Then all results contain
            | object |
            | N10 |
        When updating places
            | osm | class    | type           | admin | name+name:en | country | geometry |
            | R1  | boundary | administrative | 2     | Germany      | de      | (1,2,3,4,1) |
        When geocoding "Wenig, Loudou"
        Then exactly 0 results are returned
        When geocoding "Wenig"
            | accept-language |
            | xy,en |
        Then all results contain
            | object | display_name |
            | N10    | Wenig, Germany |


    Scenario: Default country names are always searchable
        Given the places
            | osm | class    | type          | name  |
            | N10 | place    | town          | Wenig |
        When importing
        When geocoding "Wenig, Germany"
        Then all results contain
            | object |
            | N10 |
        When geocoding "Wenig, de"
        Then all results contain
            | object |
            | N10 |
        When updating places
            | osm  | class    | type           | admin | name+name:en | country | geometry |
            | R1   | boundary | administrative | 2     | Lilly        | de      | (1,2,3,4,1) |
        When geocoding "Wenig, Germany"
            | accept-language |
            | en,de |
        Then all results contain
            | object | display_name |
            | N10 | Wenig, Lilly |
        When geocoding "Wenig, de"
            | accept-language |
            | en,de |
        Then all results contain
            | object | display_name |
            | N10    | Wenig, Lilly |


    Scenario: When a localised name is deleted, the standard name takes over
        Given the places
            | osm | class    | type           | admin | name+name:de | country | geometry |
            | R1  | boundary | administrative | 2     | Loudou       | de      | (1,2,3,4,1) |
        Given the places
            | osm | class    | type          | name  |
            | N10 | place    | town          | Wenig |
        When importing
        When geocoding "Wenig, Loudou"
            | accept-language |
            | de,en |
        Then all results contain
            | object | display_name |
            | N10 | Wenig, Loudou |
        When updating places
            | osm | class    | type           | admin | name+name:en | country | geometry |
            | R1  | boundary | administrative | 2     | Germany      | de      | (1,2,3,4,1) |
        When geocoding "Wenig, Loudou"
        Then exactly 0 results are returned
        When geocoding "Wenig"
            | accept-language |
            | de,en |
        Then all results contain
            | object | display_name |
            | N10    | Wenig, Deutschland |

