"""
CatalogIQ — Schema inference + findability scoring.

When a new product arrives with unknown attributes:
1. Vector-search similar products → infer schema
2. Map unknown attrs to canonical schema
3. Calculate findability score
4. Store mappings and score
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from es.client import get_async_es
from utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

CATALOG_IDX = "catalogsentinel-catalog"
REGISTRY_IDX = "catalogsentinel-schema-registry"
MAPPINGS_IDX = "catalogsentinel-schema-mappings"
SCORES_IDX   = "catalogsentinel-findability-scores"


class CatalogIntelligence:

    # ── Public API ──────────────────────────────────────────

    async def process_new_product(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Full pipeline for a new/updated product:
        1. Find similar products
        2. Infer schema mappings
        3. Apply mappings
        4. Calculate findability score
        5. Store everything
        """
        product_id = product.get("product_id") or str(uuid.uuid4())
        product["product_id"] = product_id

        # Step 1: Get embedding for product
        embedding = await self._embed_product(product)

        # Step 2: Find similar products by vector + keyword
        similar = await self._find_similar_products(product, embedding)

        # Step 3: Infer schema from similar products
        mappings = await self._infer_schema_mappings(product, similar)

        # Step 4: Apply mappings
        enriched = self._apply_mappings(product, mappings)

        # Step 5: Calculate findability score
        score_report = await self._calculate_findability(enriched, similar)

        # Step 6: Update product with score + embedding
        enriched["embedding"] = embedding
        enriched["findability_score"] = score_report["score"]
        enriched["schema_completeness"] = score_report["completeness"]
        enriched["ingested_at"] = datetime.utcnow().isoformat()
        enriched["updated_at"] = datetime.utcnow().isoformat()

        # Step 7: Store
        es = get_async_es()
        await es.index(index=CATALOG_IDX, id=product_id, document=enriched, refresh=True)

        # Step 8: Store mappings
        for m in mappings:
            mapping_doc = {
                "mapping_id": str(uuid.uuid4()),
                "product_id": product_id,
                "original_attr": m["original"],
                "mapped_attr": m["canonical"],
                "confidence": m["confidence"],
                "method": m["method"],
                "auto_applied": m["confidence"] >= settings.CATALOG_AUTO_MAP_CONFIDENCE,
                "created_at": datetime.utcnow().isoformat(),
            }
            await es.index(index=MAPPINGS_IDX, document=mapping_doc)

        # Step 9: Store score history
        await es.index(
            index=SCORES_IDX,
            document={
                "product_id": product_id,
                "score": score_report["score"],
                "issues": [i["field"] for i in score_report.get("issues", [])],
                "suggestions": "; ".join(i["suggestion"] for i in score_report.get("issues", [])),
                "computed_at": datetime.utcnow().isoformat(),
            },
        )

        logger.info(
            f"Product processed: {product_id} findability={score_report['score']:.1f} "
            f"mappings={len(mappings)}"
        )

        return {
            "product_id": product_id,
            "findability_score": score_report["score"],
            "schema_completeness": score_report["completeness"],
            "mappings_applied": len(mappings),
            "issues": score_report.get("issues", []),
            "estimated_visibility_gain_pct": score_report.get("visibility_gain_pct", 0),
        }

    async def get_findability_report(self, product_id: str) -> Optional[Dict]:
        es = get_async_es()
        try:
            doc = await es.get(index=CATALOG_IDX, id=product_id)
            product = doc["_source"]
        except Exception:
            return None

        similar = await self._find_similar_products(product, product.get("embedding"))
        report = await self._calculate_findability(product, similar)
        report["product_id"] = product_id
        report["product_name"] = product.get("name", "")
        return report

    async def update_schema_registry(self, category: str) -> bool:
        """
        Scan all products in a category and rebuild attribute frequency stats.
        Called nightly or when new category added.
        """
        es = get_async_es()
        try:
            resp = await es.search(
                index=CATALOG_IDX,
                query={"term": {"category": category}},
                size=0,
                aggs={
                    "attr_keys": {
                        "scripted_metric": {
                            "init_script": "state.keys = new HashMap()",
                            "map_script": """
                                if (params._source.containsKey('attributes')) {
                                    for (entry in params._source.attributes.entrySet()) {
                                        state.keys.merge(entry.getKey(), 1, Integer::sum)
                                    }
                                }
                            """,
                            "combine_script": "return state.keys",
                            "reduce_script": """
                                Map combined = new HashMap();
                                for (s in states) {
                                    for (entry in s.entrySet()) {
                                        combined.merge(entry.getKey(), entry.getValue(), Integer::sum)
                                    }
                                }
                                return combined
                            """,
                        }
                    }
                },
            )
            total = resp["hits"]["total"]["value"]
            if total == 0:
                return False

            attr_counts = resp["aggregations"]["attr_keys"]["value"] or {}
            registry_docs = []
            for attr, count in attr_counts.items():
                support_pct = count / total
                if support_pct >= settings.CATALOG_SCHEMA_INFERENCE_MIN_SUPPORT:
                    registry_docs.append({
                        "category": category,
                        "attribute_name": attr,
                        "canonical_name": attr,
                        "aliases": [],
                        "data_type": "string",
                        "support_pct": support_pct,
                        "product_count": count,
                        "sample_values": [],
                        "updated_at": datetime.utcnow().isoformat(),
                    })

            # Bulk upsert
            from elasticsearch.helpers import async_bulk
            actions = [
                {
                    "_index": REGISTRY_IDX,
                    "_id": f"{category}_{doc['attribute_name']}",
                    "_source": doc,
                }
                for doc in registry_docs
            ]
            if actions:
                await async_bulk(es, actions)
                logger.info(f"Registry updated for {category}: {len(registry_docs)} attrs")
            return True
        except Exception as e:
            logger.error(f"update_schema_registry error: {e}")
            return False

    # ── Internal helpers ─────────────────────────────────────

    async def _embed_product(self, product: Dict) -> Optional[List[float]]:
        text = f"{product.get('name', '')} {product.get('description', '')} {product.get('brand', '')}"
        try:
            from multilingual.jina_embeddings import JinaEmbeddings
            j = JinaEmbeddings()
            return await j.generate_embedding(text, task="retrieval.passage")
        except Exception as e:
            logger.warning(f"Embedding failed: {e}")
            return None

    async def _find_similar_products(
        self, product: Dict, embedding: Optional[List[float]]
    ) -> List[Dict]:
        es = get_async_es()
        category = product.get("category", "")
        try:
            if embedding:
                resp = await es.search(
                    index=CATALOG_IDX,
                    knn={
                        "field": "embedding",
                        "query_vector": embedding,
                        "k": 30,
                        "num_candidates": 100,
                        "filter": [{"term": {"category": category}}] if category else [],
                    },
                    size=30,
                )
            else:
                resp = await es.search(
                    index=CATALOG_IDX,
                    query={
                        "bool": {
                            "should": [
                                {"match": {"name": product.get("name", "")}},
                                {"term": {"category": category}},
                            ]
                        }
                    },
                    size=30,
                )
            return [h["_source"] for h in resp["hits"]["hits"]]
        except Exception as e:
            logger.warning(f"_find_similar_products error: {e}")
            return []

    async def _infer_schema_mappings(
        self, product: Dict, similar: List[Dict]
    ) -> List[Dict]:
        """
        For each attribute in product that is NOT in the registry,
        find the closest canonical attribute from similar products.
        """
        if not similar:
            return []

        product_attrs = set(product.get("attributes", {}).keys())
        category = product.get("category", "")

        # Get registry attrs for this category
        registry_attrs = await self._get_registry_attrs(category)
        canonical_set = set(registry_attrs.keys())

        # Unknown attrs = in product but not in registry
        unknown_attrs = product_attrs - canonical_set

        # Build frequency map from similar products
        attr_freq: Dict[str, int] = {}
        for p in similar:
            for attr in p.get("attributes", {}).keys():
                attr_freq[attr] = attr_freq.get(attr, 0) + 1

        mappings = []
        for unknown in unknown_attrs:
            # Try exact match with canonical
            if unknown.lower().replace("_", "") in {
                k.lower().replace("_", "") for k in canonical_set
            }:
                canonical = next(
                    k for k in canonical_set
                    if k.lower().replace("_", "") == unknown.lower().replace("_", "")
                )
                mappings.append({
                    "original": unknown,
                    "canonical": canonical,
                    "confidence": 0.95,
                    "method": "exact",
                })
                continue

            # Try semantic similarity via token overlap
            best_match, best_score = self._token_similarity(unknown, list(canonical_set | set(attr_freq.keys())))
            if best_score > 0.5:
                mappings.append({
                    "original": unknown,
                    "canonical": best_match,
                    "confidence": best_score,
                    "method": "semantic",
                })

        return mappings

    def _token_similarity(self, attr: str, candidates: List[str]) -> Tuple[str, float]:
        """Simple token overlap similarity."""
        tokens_a = set(attr.lower().replace("_", " ").split())
        best, best_score = "", 0.0
        for c in candidates:
            tokens_b = set(c.lower().replace("_", " ").split())
            if not tokens_a or not tokens_b:
                continue
            overlap = len(tokens_a & tokens_b)
            score = 2 * overlap / (len(tokens_a) + len(tokens_b))
            if score > best_score:
                best_score = score
                best = c
        return best, best_score

    def _apply_mappings(self, product: Dict, mappings: List[Dict]) -> Dict:
        """Apply auto-approved mappings to product attributes."""
        enriched = dict(product)
        attrs = dict(product.get("attributes", {}))
        for m in mappings:
            if m["confidence"] >= settings.CATALOG_AUTO_MAP_CONFIDENCE:
                val = attrs.pop(m["original"], None)
                if val is not None:
                    attrs[m["canonical"]] = val
        enriched["attributes"] = attrs
        return enriched

    async def _get_registry_attrs(self, category: str) -> Dict[str, float]:
        es = get_async_es()
        try:
            resp = await es.search(
                index=REGISTRY_IDX,
                query={"term": {"category": category}},
                size=200,
            )
            return {
                h["_source"]["canonical_name"]: h["_source"]["support_pct"]
                for h in resp["hits"]["hits"]
            }
        except Exception:
            return {}

    def _build_schema_from_similar(self, similar: List[Dict]) -> Dict[str, float]:
        """
        When registry is empty, derive expected attributes from similar products.
        Returns {attr_name: support_fraction} same format as registry.
        """
        if not similar:
            return {}
        freq: Dict[str, int] = {}
        for p in similar:
            for attr in p.get("attributes", {}).keys():
                freq[attr] = freq.get(attr, 0) + 1
        total = len(similar)
        # Only include attrs present in at least 20% of similar products
        return {
            attr: count / total
            for attr, count in freq.items()
            if count / total >= 0.2
        }

    async def _calculate_findability(
        self, product: Dict, similar: List[Dict]
    ) -> Dict:
        """
        Score 0-100. Uses registry if populated, falls back to
        schema inferred from similar products when registry is empty.

        Scoring breakdown:
          - Start: 100
          - No name:           -25
          - No brand:          -10
          - No category:       -10
          - No price:          -10
          - No description:    -10
          - Description < 30w: -10
          - No images:         -15
          - No attributes:     -20
          - Few attributes (<3):-10
          - Missing high-support attrs (>70%): -8 each (max 3)
          - Missing medium-support attrs (40-70%): -4 each (max 3)
        """
        score = 100.0
        issues = []
        category = product.get("category", "")
        product_attrs = set(product.get("attributes", {}).keys())

        # ── Basic fields ─────────────────────────────────────
        if not product.get("name", "").strip():
            score -= 25
            issues.append({"field": "name", "issue": "missing", "impact": "high",
                            "suggestion": "Product name is required"})

        if not product.get("brand", "").strip():
            score -= 10
            issues.append({"field": "brand", "issue": "missing", "impact": "medium",
                            "suggestion": "Add brand name — improves brand search visibility"})

        if not product.get("category", "").strip():
            score -= 10
            issues.append({"field": "category", "issue": "missing", "impact": "high",
                            "suggestion": "Set product category for correct classification"})

        price = product.get("price", 0)
        if not price or float(price) <= 0:
            score -= 10
            issues.append({"field": "price", "issue": "missing_or_zero", "impact": "medium",
                            "suggestion": "Set a valid price — price filters are the #1 search filter"})

        # ── Description ───────────────────────────────────────
        desc = product.get("description", "")
        desc_len = len(desc.split()) if desc else 0
        if desc_len == 0:
            score -= 10
            issues.append({"field": "description", "issue": "missing", "impact": "medium",
                            "suggestion": "Add product description — helps semantic search matching"})
        elif desc_len < 30:
            score -= 10
            issues.append({"field": "description", "issue": "too_short", "impact": "medium",
                            "suggestion": f"Description is {desc_len} words; aim for 150+ words"})

        # ── Images ────────────────────────────────────────────
        images = product.get("images", [])
        if not images:
            score -= 15
            issues.append({"field": "images", "issue": "no_images", "impact": "high",
                            "suggestion": "Add at least 3 product images (1080p recommended)"})
        elif len(images) < 3:
            score -= 5
            issues.append({"field": "images", "issue": "few_images", "impact": "medium",
                            "suggestion": f"Only {len(images)} image(s) — add at least 3 for better CTR"})

        # ── Attributes ────────────────────────────────────────
        if not product_attrs:
            score -= 20
            issues.append({"field": "attributes", "issue": "no_attributes", "impact": "high",
                            "suggestion": "Add product specifications/attributes — critical for faceted search"})
        elif len(product_attrs) < 3:
            score -= 10
            issues.append({"field": "attributes", "issue": "few_attributes", "impact": "medium",
                            "suggestion": f"Only {len(product_attrs)} attribute(s) — add more specs for filter discovery"})

        # ── Schema completeness (registry or similar-based) ───
        registry = await self._get_registry_attrs(category)

        # Fallback: build from similar products if registry empty
        if not registry and similar:
            registry = self._build_schema_from_similar(similar)
            logger.debug(f"Registry empty for '{category}', using {len(registry)} inferred attrs from {len(similar)} similar products")

        missing = []
        if registry:
            high_missing = 0
            med_missing = 0
            for attr, support in sorted(registry.items(), key=lambda x: -x[1]):
                if attr not in product_attrs:
                    if support >= 0.7 and high_missing < 3:
                        score -= 8
                        high_missing += 1
                        issues.append({
                            "field": attr, "issue": "missing", "impact": "high",
                            "suggestion": f"Add '{attr}' — present in {support*100:.0f}% of similar products",
                        })
                        missing.append(attr)
                    elif 0.4 <= support < 0.7 and med_missing < 3:
                        score -= 4
                        med_missing += 1
                        issues.append({
                            "field": attr, "issue": "missing", "impact": "medium",
                            "suggestion": f"Add '{attr}' — present in {support*100:.0f}% of similar products",
                        })
                        missing.append(attr)

        score = max(0.0, min(100.0, score))

        # Completeness ratio
        if registry:
            completeness = len(product_attrs & set(registry.keys())) / len(registry)
        else:
            # No reference: score by attribute count heuristic
            completeness = min(1.0, len(product_attrs) / 8)

        # Visibility gain
        avg_similar_score = (
            sum(p.get("findability_score", 50) for p in similar) / len(similar)
            if similar else 65
        )
        visibility_gain = max(0, avg_similar_score - score) * 3.0

        return {
            "score": round(score, 1),
            "completeness": round(completeness, 3),
            "issues": issues[:10],
            "missing_attributes": missing[:10],
            "visibility_gain_pct": round(visibility_gain, 1),
        }