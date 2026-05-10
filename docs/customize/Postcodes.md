# External postcode data

Nominatim creates a table of known postcode centroids and geometries during import.
This table is used for searches of postcodes and for adding postcodes to places where
the OSM data does not provide one. These postcode centroids are mainly computed
from the OSM data itself. In addition, Nominatim supports reading postcode information
from external files to supplement the postcodes that are missing in OSM.

## Supported file formats

To enable external postcode support, put one file per country into
your project directory and name it `<CC>_postcodes.<ext>`. `<CC>` must be the
two-letter country code for which to apply the file.

Nominatim supports CSV and JSONL (JSON lines) formats. Files may also be
gzipped, in which case the extension must be `.csv.gz` or `.jsonl.gz`.

If multiple files for the same country are present, Nominatim picks one
according to the following priority:

1. `<CC>_postcodes.jsonl`
2. `<CC>_postcodes.jsonl.gz`
3. `<CC>_postcodes.csv`
4. `<CC>_postcodes.csv.gz`

### CSV format

The CSV file must use commas as a delimiter and have a header line. Nominatim
expects three columns to be present: `postcode`, `lat` and `lon`. All other
columns are ignored. `lon` and `lat` must describe the x and y coordinates of the
postcode centroids in WGS84.

### JSONL format

The JSONL format is more detailed and supports full geometries. Each line must
contain a single JSON object. Nominatim supports two types of objects:

#### GeoJSON Feature

A standard [RFC7946](https://geojson.org) GeoJSON Feature object .

* `geometry`: A GeoJSON geometry (Point, Polygon, etc.).
* `properties`: An object containing:
  * `postcode`: (required) The postcode string.
  * `lat`, `lon`: (optional) Coordinates for the centroid. If not provided, the centroid 
  is computed from the geometry. Thus centroid coordinates and geometry are mutually optional, but exclusive
  * `extent`: (optional) An approximate geographic extent of the postcode in meters.

## Usage

As a rule, the external postcode data should be put into the project directory
**before** starting the initial import. Still, you can add, remove and update the
external postcode data at any time. Simply run:

```
nominatim refresh --postcodes
```

to make the changes visible in your database. Be aware, however, that the changes
only have an immediate effect on searches for postcodes. Postcodes that were
added to places are only updated, when they are reindexed. That usually happens
only during replication updates.
