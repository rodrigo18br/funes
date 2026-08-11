# Vector storage and search

In order to avoid remote storage of embeddings, sqlite-vector (https://github.com/sqliteai/sqlite-vector) is used to store and retrieve the generated vectors. This also avoids the concerns with running local servers and managing docker containers.

Once a text query or image is submitted for search, a similarity search from its embedding can be done in sqlite-vector using SQL:

```
CREATE TABLE images (
  id INTEGER PRIMARY KEY,
  embedding BLOB, -- store Float32/UInt8/etc.
  path TEXT
);

SELECT vector_quantize('images', 'embedding');

SELECT e.id, v.distance FROM images AS e
   JOIN vector_quantize_scan('images', 'embedding', ?) AS v
   ON e.id = v.rowid
   WHERE e.label = 'cat'
   LIMIT 10;
```

Also, sqlite-vector comes with quantization in the box using TurboQuant:

```
-- Highest recall TurboQuant mode currently recommended as the default
SELECT vector_quantize('images', 'embedding', 'qtype=TURBO,qbits=4');

-- Smaller edge-oriented representation
SELECT vector_quantize('images', 'embedding', 'qtype=TURBO2');
```
