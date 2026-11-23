"""One exact corpus/vector-space identity for ranking experiments and semantic cutoffs."""

import hashlib
import json


def retrieval_snapshot(library, db, semantic=True):
    """Bind exact source text/attribution and optionally model revision and vector bytes."""
    # BM25 uses corpus-wide document statistics even when a kind filter is applied.
    digest, count = hashlib.sha256(), 0
    for row in db.execute(
        "SELECT p.id,p.text,d.fingerprint,d.metadata FROM passages p JOIN documents d ON p.document_id=d.id ORDER BY p.id"
    ):
        digest.update(json.dumps(tuple(row), ensure_ascii=False).encode())
        count += 1
    result = {"corpus": digest.hexdigest(), "passages": count}
    if semantic:
        revision, profile = library.semantic.config(db)
        vectors = hashlib.sha256()
        for row in db.execute(
            "SELECT passage_id,content_hash,vector FROM semantic_vectors ORDER BY passage_id"
        ):
            vectors.update(json.dumps(tuple(row)[:2]).encode())
            vectors.update(row["vector"])
        result.update(
            semantic_revision=revision,
            model=profile.get("model"),
            model_digest=profile.get("model_digest"),
            **(
                {"provider": profile["provider"], "identity": profile["identity"]}
                if profile.get("provider")
                else {}
            ),
            index=vectors.hexdigest(),
        )
    return result
