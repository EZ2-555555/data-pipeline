INSERT INTO documents (
    id,
    source,
    title,
    content,
    url,
    published_at,
    content_hash,
    state,
    created_at
  )
VALUES (
    id:integer,
    'source:character varying',
    'title:text',
    'content:text',
    'url:text',
    'published_at:date',
    'content_hash:character',
    'state:character varying',
    'created_at:timestamp without time zone'
  );