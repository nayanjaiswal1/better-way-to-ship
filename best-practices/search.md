# Search — Elasticsearch / OpenSearch

Use PostgreSQL FTS (see `database.md`) for simple text search.
Use Elasticsearch / OpenSearch when you need: **faceted search, autocomplete, relevance tuning, multi-index search, or scale beyond Postgres FTS.**

## Setup

```bash
pip install elasticsearch opensearch-py  # pick one

# Docker for local dev
docker run -d --name elasticsearch \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  -p 9200:9200 \
  elasticsearch:8.12.0
```

```python
# core/search.py — single client
from elasticsearch import AsyncElasticsearch
from django.conf import settings

_client: AsyncElasticsearch | None = None

def get_search_client() -> AsyncElasticsearch:
    global _client
    if _client is None:
        _client = AsyncElasticsearch(hosts=[settings.ELASTICSEARCH_URL])
    return _client
```

```python
# config/settings/base.py
ELASTICSEARCH_URL = env("ELASTICSEARCH_URL", default="http://localhost:9200")
ELASTICSEARCH_INDEX_PREFIX = env("ELASTICSEARCH_INDEX_PREFIX", default="myapp")
```

---

## Index Definition

```python
# search/indexes.py
PRODUCT_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "id":          {"type": "keyword"},      # exact match only
            "public_id":   {"type": "keyword"},
            "tenant_id":   {"type": "integer"},      # always filter by this
            "name":        {
                "type": "text",
                "analyzer": "standard",
                "fields": {
                    "keyword": {"type": "keyword"},  # for exact match + sort
                    "suggest": {"type": "completion"},  # autocomplete
                },
            },
            "description": {"type": "text", "analyzer": "standard"},
            "tags":        {"type": "keyword"},      # facets
            "category":    {"type": "keyword"},      # facets
            "price":       {"type": "float"},
            "in_stock":    {"type": "boolean"},
            "created_at":  {"type": "date"},
            "updated_at":  {"type": "date"},
            "deleted_at":  {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards":   1,    # small: 1 shard, medium: 3-5
        "number_of_replicas": 1,    # 0 in dev, 1+ in prod
        "refresh_interval":   "1s",
    },
}

async def create_index(index: str) -> None:
    client = get_search_client()
    exists = await client.indices.exists(index=index)
    if not exists:
        await client.indices.create(index=index, body=PRODUCT_INDEX_MAPPING)
```

---

## Indexing — Keep ES in Sync with DB

### Index on Save (Django Signal)

```python
# search/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from apps.products.models import Product
from .tasks import index_product, delete_product_from_index

@receiver(post_save, sender=Product)
def on_product_saved(sender, instance, **kwargs):
    if instance.deleted_at:
        transaction.on_commit(lambda: delete_product_from_index.delay(instance.id))
    else:
        transaction.on_commit(lambda: index_product.delay(instance.id))

@receiver(post_delete, sender=Product)
def on_product_deleted(sender, instance, **kwargs):
    delete_product_from_index.delay(instance.id)
```

```python
# search/tasks.py
from celery import shared_task
from .documents import ProductDocument

@shared_task(max_retries=3, retry_backoff=True)
def index_product(product_id: int) -> None:
    from apps.products.models import Product
    try:
        product = Product.all_objects.select_related("category").get(id=product_id)
        ProductDocument().index(product)
    except Product.DoesNotExist:
        pass

@shared_task
def delete_product_from_index(product_id: int) -> None:
    ProductDocument().delete(product_id)

@shared_task
def reindex_all_products(tenant_id: int | None = None) -> dict:
    """Full reindex — run after mapping changes."""
    from apps.products.models import Product
    qs = Product.all_objects.filter(deleted_at__isnull=True)
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)

    count = 0
    for product in qs.iterator(chunk_size=500):
        index_product.delay(product.id)
        count += 1

    return {"queued": count}
```

```python
# search/documents.py
import asyncio
from .indexes import get_search_client

class ProductDocument:
    INDEX = "myapp_products"

    def to_document(self, product) -> dict:
        return {
            "id":          product.id,
            "public_id":   product.public_id,
            "tenant_id":   product.tenant_id,
            "name":        product.name,
            "description": product.description or "",
            "tags":        list(product.tags.values_list("name", flat=True)),
            "category":    product.category.name if product.category else None,
            "price":       float(product.price),
            "in_stock":    product.in_stock,
            "created_at":  product.created_at.isoformat(),
            "updated_at":  product.updated_at.isoformat(),
        }

    def index(self, product) -> None:
        client = get_search_client()
        doc = self.to_document(product)
        asyncio.run(client.index(index=self.INDEX, id=str(product.id), document=doc))

    def delete(self, product_id: int) -> None:
        client = get_search_client()
        asyncio.run(client.delete(index=self.INDEX, id=str(product_id), ignore=[404]))
```

---

## Full-Text Search

```python
# search/queries.py
from dataclasses import dataclass, field
from .indexes import get_search_client

@dataclass
class SearchParams:
    query:     str
    tenant_id: int
    category:  str | None = None
    tags:      list[str] = field(default_factory=list)
    min_price: float | None = None
    max_price: float | None = None
    in_stock:  bool | None = None
    page:      int = 1
    page_size: int = 20
    sort:      str = "_score"    # _score | price | -price | created_at

@dataclass
class SearchResult:
    hits:       list[dict]
    total:      int
    facets:     dict
    page:       int
    page_size:  int
    took_ms:    int

async def search_products(params: SearchParams) -> SearchResult:
    client = get_search_client()

    # Build query
    must = [{"term": {"tenant_id": params.tenant_id}}]
    filter_clauses = []

    if params.query:
        must.append({
            "multi_match": {
                "query":  params.query,
                "fields": ["name^3", "description", "tags"],  # name weighted 3x
                "type":   "best_fields",
                "fuzziness": "AUTO",  # tolerate typos
            }
        })

    if params.category:
        filter_clauses.append({"term": {"category": params.category}})

    if params.tags:
        filter_clauses.append({"terms": {"tags": params.tags}})

    if params.in_stock is not None:
        filter_clauses.append({"term": {"in_stock": params.in_stock}})

    if params.min_price or params.max_price:
        price_range = {}
        if params.min_price: price_range["gte"] = params.min_price
        if params.max_price: price_range["lte"] = params.max_price
        filter_clauses.append({"range": {"price": price_range}})

    # Sort
    sort_map = {
        "_score":     [{"_score": "desc"}],
        "price":      [{"price": "asc"}],
        "-price":     [{"price": "desc"}],
        "created_at": [{"created_at": "desc"}],
    }
    sort = sort_map.get(params.sort, sort_map["_score"])

    body = {
        "query": {
            "bool": {
                "must":   must,
                "filter": filter_clauses,
            }
        },
        "sort": sort,
        "from": (params.page - 1) * params.page_size,
        "size": params.page_size,
        # Aggregations — for facets/filters UI
        "aggs": {
            "categories": {"terms": {"field": "category", "size": 20}},
            "tags":       {"terms": {"field": "tags",     "size": 50}},
            "price_range": {
                "stats": {"field": "price"}
            },
            "in_stock_count": {"filter": {"term": {"in_stock": True}}},
        },
    }

    result = await client.search(index="myapp_products", body=body)

    hits = [{"_score": h["_score"], **h["_source"]} for h in result["hits"]["hits"]]
    aggs = result.get("aggregations", {})

    return SearchResult(
        hits=hits,
        total=result["hits"]["total"]["value"],
        facets={
            "categories": [{"value": b["key"], "count": b["doc_count"]} for b in aggs.get("categories", {}).get("buckets", [])],
            "tags":       [{"value": b["key"], "count": b["doc_count"]} for b in aggs.get("tags", {}).get("buckets", [])],
            "price":      aggs.get("price_range", {}),
            "in_stock":   aggs.get("in_stock_count", {}).get("doc_count", 0),
        },
        page=params.page,
        page_size=params.page_size,
        took_ms=result["took"],
    )
```

---

## Autocomplete

```python
# search/queries.py
async def autocomplete_products(query: str, tenant_id: int, limit: int = 10) -> list[str]:
    """Fast autocomplete using completion suggester."""
    client = get_search_client()

    result = await client.search(
        index="myapp_products",
        body={
            "_source": ["name"],
            "suggest": {
                "product_suggest": {
                    "prefix": query,
                    "completion": {
                        "field": "name.suggest",
                        "size":  limit,
                        "contexts": {
                            # Only suggest from user's tenant
                            "tenant_id": [{"context": str(tenant_id)}]
                        },
                    },
                }
            },
        },
    )

    suggestions = result.get("suggest", {}).get("product_suggest", [{}])[0].get("options", [])
    return [s["_source"]["name"] for s in suggestions]
```

---

## FastAPI Integration

```python
# api/v1/search.py
from fastapi import APIRouter, Query, Depends
from search.queries import SearchParams, search_products, autocomplete_products

router = APIRouter(prefix="/search", tags=["search"])

@router.get("/products")
async def search(
    q:         str | None = Query(None),
    category:  str | None = None,
    tags:      list[str]  = Query(default=[]),
    min_price: float | None = None,
    max_price: float | None = None,
    in_stock:  bool | None = None,
    page:      int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
    sort:      str = "_score",
    current_user: User = Depends(get_current_user),
):
    params = SearchParams(
        query=q or "",
        tenant_id=current_user.tenant_id,
        category=category,
        tags=tags,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return await search_products(params)

@router.get("/autocomplete")
async def autocomplete(
    q: str = Query(min_length=2),
    current_user: User = Depends(get_current_user),
):
    suggestions = await autocomplete_products(q, current_user.tenant_id)
    return {"suggestions": suggestions}
```

## Django/DRF Integration

```python
# apps/search/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from asgiref.sync import async_to_sync
from search.queries import SearchParams, search_products

class ProductSearchView(APIView):
    def get(self, request):
        params = SearchParams(
            query=request.query_params.get("q", ""),
            tenant_id=request.user.tenant_id,
            category=request.query_params.get("category"),
            page=int(request.query_params.get("page", 1)),
            page_size=int(request.query_params.get("page_size", 20)),
        )
        result = async_to_sync(search_products)(params)
        return Response({
            "data":       result.hits,
            "total":      result.total,
            "facets":     result.facets,
            "took_ms":    result.took_ms,
            "pagination": {
                "page":       result.page,
                "page_size":  result.page_size,
                "total_pages": -(-result.total // result.page_size),
            },
        })
```

---

## React — Search UI

```tsx
// hooks/useSearch.ts
export function useSearch(resource: string) {
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const debouncedQuery = useDebounce(query, 300);

  const results = useQuery({
    queryKey: [resource, 'search', debouncedQuery, filters],
    queryFn: () => api.get(`/search/${resource}`, { params: { q: debouncedQuery, ...filters } }),
    enabled: debouncedQuery.length > 1 || Object.keys(filters).length > 0,
    staleTime: 30_000,
  });

  return { query, setQuery, filters, setFilters, ...results };
}

// Search UI — facets driven from backend aggregations
function ProductSearch() {
  const { query, setQuery, data, filters, setFilters } = useSearch('products');

  return (
    <div>
      <SearchInput value={query} onChange={setQuery} />
      <div className="layout">
        <aside>
          {/* Facets from ES aggregations — backend-driven, never hardcoded */}
          {data?.facets.categories.map(cat => (
            <FacetItem
              key={cat.value}
              label={cat.value}
              count={cat.count}
              active={filters.category === cat.value}
              onClick={() => setFilters(f => ({ ...f, category: cat.value }))}
            />
          ))}
        </aside>
        <main>
          {data?.data.map(product => <ProductCard key={product.id} product={product} />)}
        </main>
      </div>
    </div>
  );
}
```

---

## Search Checklist

- [ ] Always filter by `tenant_id` in every search query — tenant isolation
- [ ] Indexing via Celery task on `post_save` signal — not synchronous
- [ ] `transaction.on_commit` before firing index task — avoids race condition
- [ ] Full reindex task for schema/mapping changes
- [ ] Facets returned from aggregations — frontend never hardcodes filter values
- [ ] Autocomplete via `completion` suggester — not another full-text query
- [ ] Fuzziness enabled for typo tolerance (`"fuzziness": "AUTO"`)
- [ ] Field weighting — `name^3` ranked higher than `description`
- [ ] `number_of_replicas: 1` in production — zero in dev
- [ ] Index name includes prefix (`myapp_products`) — avoid collisions on shared clusters
- [ ] Deleted documents removed from index (soft delete → signal → delete task)
