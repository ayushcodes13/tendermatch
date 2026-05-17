# TenderMatch System Overview

## Architecture Overview

The TenderMatch system is a tender matching pipeline that scrapes government procurement data, filters relevant tenders, and matches them with manufacturers who can supply the needed equipment.

The architecture follows a clear pipeline:
```
run.py (orchestrator)
├── scrapers/cppp.py (data collection)
├── data/db.py (storage)
├── matching/filter.py (classification)
└── matching/matcher.py (semantic matching)
```

## System Components

### 1. Pipeline Orchestrator (`pipeline/run.py`)

The main orchestrator script coordinates the entire process:

1. **Data Collection**: Scrapes tenders from government portals (central, state, GEM)
2. **Deduplication**: Prevents processing the same tender multiple times using content hashing
3. **Classification**: Filters tenders into blocked/low_signal/high_signal categories
4. **Matching**: For high-signal tenders, finds relevant manufacturers using semantic matching
5. **Storage**: Updates database with processing flags

### 2. Web Scraping (`scrapers/cppp.py`)

This module scrapes government procurement portals:

**Data Sources**:
- Central portal: `https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata`
- State portal: `https://eprocure.gov.in/cppp/latestactivetendersnew/mmpdata`
- GEM portal: `https://eprocure.gov.in/cppp/latestactivetendersnew/gemdata`

**Scraping Logic**:
- Fetches pages with retry logic and rate limiting
- Parses tender rows with source-specific parsers
- Handles both GEM-specific and general tender formats
- Stops scraping when reaching old tenders (24-hour cutoff)

**Data Model**:
```python
{
    "tender_id": "Unique identifier",
    "title": "Tender title",
    "organization": "Issuing organization",
    "published_date": "Publication date",
    "closing_date": "Closing date",
    "source_url": "Direct link to tender",
    "raw_text": "Combined searchable text",
    "source_portal": "central/state/gem",
    "scraped_at": "Timestamp"
}
```

### 3. Database Management (`data/db.py`)

SQLite-based storage with automatic deduplication:

**Schema**:
- `tenders` table with fields for all tender data
- `content_hash` for deduplication (title+organization+date)
- Unique constraint on tender_id + content_hash

### 4. Tender Classification (`matching/filter.py`)

Two-stage filtering system:

**Blocklist Filtering** (substring-based):
- Words like "road", "construction", "civil", "repair", etc.
- Immediately blocks irrelevant tenders

**Positive Signal Detection** (hybrid matching):
- Phrase matching for "testing equipment", "analytical instrument", etc.
- Categorizes as blocked/low_signal/high_signal

### 5. Semantic Matching (`matching/embedder.py` & `matching/matcher.py`)

Advanced manufacturer matching using sentence transformers:

**Embedder**:
- Uses `BAAI/bge-small-en-v1.5` model for text embeddings
- Pre-processes manufacturer profiles into searchable vectors
- Handles manufacturer aliases and product categories

**Matcher**:
- Converts tender text to embeddings
- Computes cosine similarity with manufacturer profiles
- Returns top 3 most relevant manufacturers with confidence scores

### 6. Manufacturer Profiles (`data/manufacturers.json`)

Comprehensive database of 20+ specialized equipment manufacturers:

**Profile Structure**:
```json
{
  "id": "Unique identifier",
  "name": "Company name",
  "aliases": "Alternative names",
  "country": "Location",
  "product_categories": "Specialized products",
  "embedding_text": "Detailed description for semantic matching",
  "keywords": "Search terms",
  "website": "Company website"
}
```

### 7. Data Flow Process

1. **Scraping**: Collect latest tenders from government portals
2. **Deduplication**: Skip already-processed tenders using content hashing
3. **Classification**: Filter tenders using keyword-based rules
4. **Semantic Matching**: For high-signal tenders, find relevant manufacturers
5. **Storage**: Update database with results and flags
6. **Reporting**: Output classification statistics

### 8. Key Features

**Intelligent Filtering**:
- Blocklist prevents processing irrelevant tenders
- Positive keyword detection identifies opportunities
- Hybrid matching for precision (phrases vs. words)

**Semantic Intelligence**:
- Embedding-based manufacturer matching
- Confidence scoring for match quality
- Specialized equipment domain knowledge

**Efficiency**:
- Automatic deduplication prevents redundant processing
- Content-based cutoff stops at old tenders
- Database storage for historical tracking