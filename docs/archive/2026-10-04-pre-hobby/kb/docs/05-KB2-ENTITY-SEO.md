# KB-2: 实体索引+SEO (2天)

## Goal
Build entity→article index, SEO structured data, sitemap, and internal linking network.

## Tasks
1. Read entity_buffer/*.json and canonical_map.json → build entity→articles mapping
2. Generate entity pages (entities/{slug}.html)
3. Implement JSON-LD structured data on all page types:
   - Article (headline, author, datePublished, image, keywords)
   - CollectionPage (topic pillar pages)
   - Thing (entity pages)
   - BreadcrumbList (all pages)
   - FAQPage (ask page with hot questions)
4. Generate sitemap.xml with all article/topic/entity URLs
5. Generate robots.txt
6. Implement article→entity, entity→article, article→article related links

## Data Sources
- entity_buffer/*.json — per-article extracted entities (from LightRAG ingest)
- canonical_map.json — entity alias normalization
- SQLite entity_canonical table — canonical entity names

## Entity Index Format (in-memory, built at export time)
```python
entity_index = {
    "OpenAI": {
        "canonical_name": "OpenAI",
        "aliases": ["openai", "open-ai"],
        "type": "organization",
        "article_hashes": ["abc123", "def456"]
    },
    ...
}
```

## SEO Requirements
- Every page: <html lang="zh-CN"> + hreflang
- Every page: og:title, og:description, og:image, og:type
- Article pages: Article schema + BreadcrumbList
- Topic pages: CollectionPage schema
- Entity pages: Thing schema
- Ask page: FAQPage schema (hot questions)
- All pages: Organization schema (publisher)
