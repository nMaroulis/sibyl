"""Owner judgments, actual rankings, frozen corpora and durable cancellation fences."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_research_library import library as library
from test_semantic_research import semantic as semantic

from sibyl.research_library.evaluations.contracts import EvaluationRun, EvaluationSuite
from sibyl.research_library.evaluations.metrics import score
from sibyl.research_library.evaluations.service import RetrievalEvaluations


def suite(library):
    relevant = library.import_document("liquidity.txt", b"A reserve of liquid assets supports redemption.")
    library.import_document("mining.txt", b"Proof of work miners propose a network block.")
    return library.evaluations.save(
        EvaluationSuite(
            title="Redemption relevance",
            kind="document",
            cases=[{"query": "liquid reserve redemption", "expected": [relevant["passages"][0]["id"]]}],
        )
    )


def test_metric_math_empty_retrieval_and_fixed_precision_denominator():
    assert score([], ["a"], 5) == {"precision": 0, "recall": 0, "reciprocal_rank": 0, "ndcg": 0, "hit": 0}
    result = score(["z", "a", "b"], ["a", "b"], 5)
    assert result["precision"] == 0.4 and result["recall"] == 1 and result["reciprocal_rank"] == 0.5
    assert 0 < result["ndcg"] < 1


def test_keyword_uses_actual_search_and_retains_exact_citations_without_model(library, monkeypatch):
    definition = suite(library)
    monkeypatch.setattr(
        library.semantic.provider, "embed", lambda *a: pytest.fail("Keyword contacted a model")
    )
    item = library.evaluations.start(definition["id"], EvaluationRun(k=5))
    library.evaluations.tick()
    saved = library.evaluations.get(item["id"])
    assert saved["state"] == "completed"
    assert saved["summary"]["keyword"]["precision"] == 0.2
    assert saved["summary"]["keyword"]["recall"] == 1
    assert saved["results"][0]["items"][0]["id"] == definition["cases"][0]["expected"][0]
    assert saved["suite"]["gold"][0][0]["text"] == saved["results"][0]["items"][0]["text"]
    assert RetrievalEvaluations(library).get(item["id"]) == saved
    repeated = library.evaluations.start(definition["id"], EvaluationRun(k=5))
    library.evaluations.tick()
    assert library.evaluations.get(repeated["id"])["summary"]["keyword"]["ndcg"] == 1


@pytest.mark.parametrize("mutation", ["import", "remove", "index"])
def test_changed_corpus_or_semantic_revision_invalidates_whole_comparison(library, mutation):
    definition = suite(library)
    body = EvaluationRun()
    if mutation == "index":
        # No fake quality claims: create only enough explicit index metadata to test its fence.
        with library.db() as db:
            db.execute("UPDATE semantic_settings SET revision=1,payload='{}'")
        body = EvaluationRun(methods=["keyword"])
    item = library.evaluations.start(definition["id"], body)
    if mutation == "import":
        library.import_document("new.txt", b"Additional liquid reserve evidence.")
    elif mutation == "remove":
        library.delete(definition["gold"][0][0]["document_id"])
    else:
        library.reindex(definition["gold"][0][0]["document_id"])
        # Keyword does not depend on embedding settings, but reindex metadata is part of its corpus.
    library.evaluations.tick()
    assert library.evaluations.get(item["id"])["state"] == "failed"
    assert library.evaluations.get(item["id"])["summary"] == {}


def test_stop_during_blocking_search_discards_late_success_and_close_drains(library, monkeypatch):
    definition = suite(library)
    entered, release = threading.Event(), threading.Event()
    search = library.search

    def blocking(*args):
        entered.set()
        assert release.wait(5)
        return search(*args)

    monkeypatch.setattr(library, "search", blocking)
    item = library.evaluations.start(definition["id"], EvaluationRun())
    with ThreadPoolExecutor(2) as pool:
        future = pool.submit(library.evaluations.tick)
        assert entered.wait(5)
        library.evaluations.stop(item["id"])
        closed = pool.submit(library.evaluations.close)
        assert not closed.done()
        release.set()
        future.result(5)
        closed.result(5)
    saved = library.evaluations.get(item["id"])
    assert saved["state"] == "stopped" and not saved["results"]


def test_restart_marks_interrupted_no_automatic_replay_and_gold_removal_blocks_new_run(library):
    definition = suite(library)
    item = library.evaluations.start(definition["id"], EvaluationRun())
    restarted = RetrievalEvaluations(library)
    assert restarted.get(item["id"])["state"] == "interrupted"
    restarted.tick()
    assert restarted.get(item["id"])["state"] == "interrupted"
    library.delete(definition["gold"][0][0]["document_id"])
    with pytest.raises(ValueError, match="labeled passage"):
        restarted.start(definition["id"], EvaluationRun())


def test_api_no_store_bounded_validation_and_semantic_requires_explicit_setup(manual_client):
    service = manual_client.app.state.services.library
    definition = suite(service)
    response = manual_client.get("/api/v1/library/evaluations")
    assert response.headers["cache-control"] == "no-store"
    response = manual_client.post(
        f"/api/v1/library/evaluations/suites/{definition['id']}/runs", json={"methods": ["semantic"]}
    )
    assert response.status_code == 400
    response = manual_client.post(
        f"/api/v1/library/evaluations/suites/{definition['id']}/runs", json={"k": True}
    )
    assert response.status_code == 422
    response = manual_client.post(f"/api/v1/library/evaluations/suites/{definition['id']}/runs", json={})
    assert response.status_code == 202
    service.evaluations.tick()
    assert (
        manual_client.get(f"/api/v1/library/evaluations/runs/{response.json()['id']}").json()["state"]
        == "completed"
    )


def test_semantic_methods_compare_identical_queries_and_profile_changes_fence_results(semantic):
    from test_semantic_research import configure, index, sources

    library, server = semantic
    docs = sources(library)
    configure(library)
    index(library)
    definition = library.evaluations.save(
        EvaluationSuite(
            title="Topic ranking contracts",
            cases=[{"query": "private key custody", "expected": [docs[0]["passages"][0]["id"]]}],
        )
    )
    item = library.evaluations.start(
        definition["id"], EvaluationRun(methods=["keyword", "semantic", "hybrid"], k=3)
    )
    for _ in range(3):
        library.evaluations.tick()
    saved = library.evaluations.get(item["id"])
    assert saved["state"] == "completed" and len(saved["results"]) == 3
    assert set(saved["summary"]) == {"keyword", "semantic", "hybrid"}
    assert saved["snapshot"]["model_digest"] == server.digest
    assert all(row["metrics"]["recall"] == 1 for row in saved["results"])
    item = library.evaluations.start(definition["id"], EvaluationRun(methods=["semantic"]))
    library.semantic.clear(library.semantic.status()["revision"])
    library.evaluations.tick()
    assert library.evaluations.get(item["id"])["state"] == "failed"


def test_native_agents_read_saved_quality_evidence_without_starting_jobs(manual_client, monkeypatch):
    from test_agent_guidance import tool_call

    library = manual_client.app.state.services.library
    definition = suite(library)
    item = library.evaluations.start(definition["id"], EvaluationRun())
    library.evaluations.tick()
    monkeypatch.setattr(library.evaluations, "start", lambda *a: pytest.fail("Agent started an evaluation"))
    for module in ("wiki", "reporter"):
        result = tool_call(manual_client, module, "retrieval_evaluation", evaluation_id=item["id"])
        assert result["id"] == item["id"] and result["summary"]["keyword"]["recall"] == 1
        assert result["queries"][0]["citations"][0]["url"].startswith("/research?")
    response = manual_client.post(
        "/api/v1/agents/ask",
        json={
            "module": "wiki",
            "message": "Explain this evaluation",
            "context": {"retrieval_evaluation_id": item["id"]},
        },
    )
    assert response.status_code == 200
    assert response.json()["tool"] == "retrieval_evaluation"


def test_only_one_job_is_admitted_and_stop_releases_queue(library):
    definition = suite(library)
    item = library.evaluations.start(definition["id"], EvaluationRun())
    with pytest.raises(ValueError, match="already active"):
        library.evaluations.start(definition["id"], EvaluationRun())
    with pytest.raises(ValueError, match="Stop"):
        library.evaluations.delete(definition["id"])
    library.evaluations.stop(item["id"])
    fresh = library.evaluations.start(definition["id"], EvaluationRun())
    assert fresh["id"] != item["id"]
