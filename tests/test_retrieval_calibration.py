"""Real local/hosted ranking contracts with controlled embeddings, not model-quality acceptance."""

import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError
from test_hosted_embeddings import hosted as hosted
from test_hosted_embeddings import server as server
from test_research_library import library as library
from test_semantic_research import configure, index, sources
from test_semantic_research import semantic as semantic

from sibyl.research_library.calibration.contracts import CalibrationCreate, CalibrationPolicy
from sibyl.research_library.calibration.metrics import calibrate, metrics
from sibyl.research_library.calibration.service import RetrievalCalibration


def definition(library, expected, **kwargs):
    cases = []
    for partition in ("fit", "validation"):
        cases += [
            {"query": f"custodian {partition} question {i}", "partition": partition, "expected": [expected]}
            for i in range(2)
        ]
        cases += [
            {"query": f"missing {partition} question {i}", "partition": partition, "expected": []}
            for i in range(2)
        ]
    return CalibrationCreate(title="Separate held-out labels", cases=cases, **kwargs)


def prepare(semantic):
    library, server = semantic
    docs = sources(library)
    configure(library)
    index(library)
    return library, server, docs


def finish(library, body):
    item = library.calibration.start(body)
    for _ in body.cases:
        library.calibration.tick()
    result = library.calibration.get(item["id"])
    assert result["state"] == "completed", result
    return result


def enable(library, report):
    kind = report["kind"]
    previous = library.calibration.status()["policies"][kind]
    return library.calibration.set_policy(
        kind, CalibrationPolicy(revision=previous["revision"], enabled=True, report_id=report["id"])
    )


def test_actual_rankings_fit_cutoff_without_validation_leak_and_remain_disabled(semantic):
    library, server, docs = prepare(semantic)
    result = finish(library, definition(library, docs[0]["passages"][0]["id"]))
    c = result["calibration"]
    bad = [r["similarity"] for r in result["results"] if r["partition"] == "fit" and not r["expected"]]
    assert bad[0] == pytest.approx(1 / math.sqrt(3), abs=1e-6)
    assert c["threshold"] == math.nextafter(max(bad), math.inf)
    assert c["eligible"] and c["validation"]["correct_accepts"] == 2
    assert c["validation"]["incorrect_accepts"] == 0 and c["validation"]["no_source"] == 2
    assert not library.calibration.status()["policies"]["document"]["enabled"]
    assert result["results"][0]["citation"]["text"] == docs[0]["passages"][0]["text"]
    assert result["gold"][0][0]["url"].startswith("/research?")
    assert RetrievalCalibration(library).get(result["id"]) == result
    assert library.calibration.status()["reports"][0]["snapshot_current"]
    assert all("cases" not in r and "results" not in r for r in library.calibration.status()["reports"])


def test_held_out_failures_never_retune_threshold_and_block_activation(semantic):
    library, server, docs = prepare(semantic)
    body = definition(library, docs[0]["passages"][0]["id"])
    # A no-source validation question maps to a high-score passage: it must fail,
    # not increase the threshold using held-out labels.
    body.cases[-1].query = "custodian unsupported held-out claim"
    result = finish(library, body)
    assert not result["calibration"]["eligible"]
    assert result["calibration"]["threshold"] < 1
    assert result["calibration"]["validation"]["accepted_no_source"] == 1
    with pytest.raises(ValueError, match="held-out"):
        enable(library, result)


def test_ties_wrong_positive_matches_and_no_accepted_questions_are_explicit():
    rows = [
        {
            "query": str(i),
            "partition": p,
            "expected": ["a"] if i % 2 else [],
            "passage_id": "a",
            "similarity": 1.0,
        }
        for p in ("fit", "validation")
        for i in range(4)
    ]
    c = calibrate(rows)
    assert c["threshold"] > 1 and not c["eligible"]
    assert c["validation"]["accepted"] == 0 and c["validation"]["precision"] is None
    assert metrics([dict(rows[1], passage_id="wrong")], 0)["incorrect_accepts"] == 1
    assert metrics([dict(rows[1], passage_id=None, similarity=None)], -1)["missed_answerable"] == 1


def test_policy_is_explicit_exact_scope_top_one_and_rejects_reused_revision(semantic):
    library, server, docs = prepare(semantic)
    result = finish(library, definition(library, docs[0]["passages"][0]["id"]))
    state = enable(library, result)
    assert state["policies"]["document"]["state"] == "active"
    found = library.search("custodian unfamiliar wording", "document", 20, "semantic")
    assert len(found["items"]) == 1 and found["calibration"]["state"] == "accepted"
    assert found["items"][0]["id"] == docs[0]["passages"][0]["id"]
    absent = library.search("unrelated unsupported claim", "document", 20, "semantic")
    assert absent["items"] == [] and absent["calibration"]["abstained"]
    assert "text" not in json.dumps(absent["calibration"])
    assert len(library.search("custodian", "all", 20, "semantic")["items"]) == 3
    assert not library.search("custodian", "all", 20, "semantic")["calibration"]["applied"]
    assert library.search("custodian", "document", 20, "keyword")["items"]
    assert len(library.search("custodian", "document", 20, "hybrid")["items"]) == 3
    with pytest.raises(ValueError, match="changed"):
        library.calibration.set_policy("document", CalibrationPolicy(revision=0, enabled=False))
    library.calibration.set_policy("document", CalibrationPolicy(revision=1, enabled=False))
    assert len(library.search("unsupported claim", "document", 20, "semantic")["items"]) == 3


@pytest.mark.parametrize("mutation", ["new_source", "remove", "reindex", "clear", "profile"])
def test_changed_bindings_withhold_before_any_embedding_request(semantic, mutation):
    library, server, docs = prepare(semantic)
    result = finish(library, definition(library, docs[0]["passages"][0]["id"]))
    enable(library, result)
    if mutation == "new_source":
        library.import_document("new.txt", b"An additional retained observation.")
    elif mutation == "remove":
        library.delete(docs[1]["id"])
    elif mutation == "reindex":
        library.reindex(docs[1]["id"])
    elif mutation == "clear":
        library.semantic.clear(library.semantic.status()["revision"])
    else:
        configure(library)
    count = len(server.calls)
    response = library.search("custodian", "document", 8, "semantic")
    assert response["items"] == [] and response["calibration"]["state"] == "stale"
    assert len(server.calls) == count
    assert not library.calibration.status()["reports"][0]["snapshot_current"]
    with pytest.raises(ValueError, match="changed"):
        enable(library, result)


@pytest.mark.parametrize("change", ["policy", "corpus"])
def test_inflight_policy_or_source_changes_never_release_late_passages(semantic, monkeypatch, change):
    library, server, docs = prepare(semantic)
    result = finish(library, definition(library, docs[0]["passages"][0]["id"]))
    enable(library, result)
    original = library.semantic.search
    entered, release = threading.Event(), threading.Event()

    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(library.semantic, "search", blocked)
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(library.search, "custodian", "document", 8, "semantic")
        assert entered.wait(5)
        if change == "policy":
            library.calibration.set_policy("document", CalibrationPolicy(revision=1, enabled=False))
        else:
            library.import_document("new.txt", b"New source while retrieval was underway.")
        release.set()
        found = pending.result(5)
    assert found["items"] == [] and found["calibration"]["state"] == "changed"


def test_enabling_during_an_unguarded_search_also_fences_results(semantic, monkeypatch):
    library, server, docs = prepare(semantic)
    result = finish(library, definition(library, docs[0]["passages"][0]["id"]))
    raw = library.semantic.search

    def changing(*args):
        found = raw(*args)
        enable(library, result)
        return found

    monkeypatch.setattr(library.semantic, "search", changing)
    found = library.search("missing observation", "document", 8, "semantic")
    assert not found["items"] and found["calibration"]["state"] == "changed"


def test_stop_fences_a_blocking_query_and_close_drains_it(semantic, monkeypatch):
    library, server, docs = prepare(semantic)
    body = definition(library, docs[0]["passages"][0]["id"])
    item = library.calibration.start(body)
    original = library.search
    entered, release = threading.Event(), threading.Event()

    def blocking(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(library, "search", blocking)
    with ThreadPoolExecutor(2) as pool:
        pending = pool.submit(library.calibration.tick)
        assert entered.wait(5)
        library.calibration.stop(item["id"])
        closing = pool.submit(library.calibration.close)
        assert not closing.done()
        release.set()
        pending.result(5)
        closing.result(5)
    assert library.calibration.get(item["id"])["state"] == "stopped"
    assert library.calibration.get(item["id"])["results"] == []


def test_restart_interruption_errors_and_deletion_leave_policies_off(semantic, monkeypatch):
    library, server, docs = prepare(semantic)
    body = definition(library, docs[0]["passages"][0]["id"])
    item = library.calibration.start(body)
    with pytest.raises(ValueError, match="active"):
        library.calibration.start(body)
    with pytest.raises(ValueError, match="Stop"):
        library.calibration.delete(item["id"])
    restarted = RetrievalCalibration(library)
    assert restarted.get(item["id"])["state"] == "interrupted"
    restarted.tick()
    assert not restarted.get(item["id"])["results"]
    library.calibration.delete(item["id"])
    broken = library.calibration.start(body)
    monkeypatch.setattr(
        library, "search", lambda *args: (_ for _ in ()).throw(RuntimeError("PRIVATE-PROVIDER-KEY"))
    )
    library.calibration.tick()
    result = library.calibration.get(broken["id"])
    assert result["state"] == "failed" and result["calibration"] is None
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("mutation", ["corpus", "index"])
def test_experiment_change_after_network_call_cannot_commit_partial_results(semantic, monkeypatch, mutation):
    library, server, docs = prepare(semantic)
    item = library.calibration.start(definition(library, docs[0]["passages"][0]["id"]))
    raw = library.search

    def changing(*args):
        found = raw(*args)
        if mutation == "corpus":
            library.import_document("new.txt", b"New material invalidates calibration.")
        else:
            library.semantic.clear(library.semantic.status()["revision"])
        return found

    monkeypatch.setattr(library, "search", changing)
    library.calibration.tick()
    result = library.calibration.get(item["id"])
    assert result["state"] == "failed" and result["results"] == []


def test_active_report_cannot_be_deleted_and_restart_preserves_policy(semantic):
    library, server, docs = prepare(semantic)
    result = finish(library, definition(library, docs[0]["passages"][0]["id"]))
    enable(library, result)
    restarted = RetrievalCalibration(library)
    assert restarted.status()["policies"]["document"]["enabled"]
    with pytest.raises(ValueError, match="Disable"):
        restarted.delete(result["id"])
    restarted.set_policy("document", CalibrationPolicy(revision=1, enabled=False))
    restarted.delete(result["id"])
    assert not restarted.status()["reports"]


def test_admission_requires_complete_scope_index_and_scoped_labels(semantic):
    library, server = semantic
    docs = sources(library)
    body = definition(library, docs[0]["passages"][0]["id"])
    with pytest.raises(ValueError, match="completely"):
        library.calibration.start(body)
    configure(library)
    index(library, limit=1)
    with pytest.raises(ValueError, match="completely"):
        library.calibration.start(body)
    index(library)
    invalid = body.model_copy(deep=True)
    invalid.cases[0].expected = ["news-" + "a" * 32 + "-0-" + "b" * 12]
    with pytest.raises(ValueError, match="scope"):
        library.calibration.start(invalid)


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "missing_negatives", "missing_positive", "empty_query", "duplicate_id", "oversized"],
)
def test_label_contracts_reject_ambiguous_or_unbounded_experiments(mutation):
    body = definition(None, "a" * 32 + "-0-" + "b" * 12).model_dump()
    if mutation == "duplicate":
        body["cases"][-1]["query"] = body["cases"][0]["query"].upper()
    elif mutation == "missing_negatives":
        body["cases"][3]["expected"] = body["cases"][0]["expected"]
    elif mutation == "missing_positive":
        body["cases"][0]["expected"] = []
    elif mutation == "empty_query":
        body["cases"][0]["query"] = "  "
    elif mutation == "duplicate_id":
        body["cases"][0]["expected"] *= 2
    else:
        body["cases"] *= 5
    with pytest.raises(ValidationError):
        CalibrationCreate(**body)


def test_raw_ranking_evaluations_are_not_biased_by_an_active_cutoff(semantic):
    from sibyl.research_library.evaluations.contracts import EvaluationRun, EvaluationSuite

    library, server, docs = prepare(semantic)
    result = finish(library, definition(library, docs[0]["passages"][0]["id"]))
    enable(library, result)
    suite = library.evaluations.save(
        EvaluationSuite(
            title="Raw rankings",
            kind="document",
            cases=[{"query": "missing from the corpus", "expected": [docs[0]["passages"][0]["id"]]}],
        )
    )
    report = library.evaluations.start(suite["id"], EvaluationRun(methods=["semantic"], k=3))
    library.evaluations.tick()
    found = library.evaluations.get(report["id"])
    assert len(found["results"][0]["items"]) == 3


def test_private_http_controls_and_native_agent_use_actual_receipts(manual_client, monkeypatch):
    from test_agent_guidance import tool_call
    from test_semantic_research import EmbeddingServer

    from sibyl.research_library.semantic.provider import OllamaEmbeddings

    library = manual_client.app.state.services.library
    server = EmbeddingServer()
    library.semantic.provider = OllamaEmbeddings(server.client)
    library, server, docs = prepare((library, server))
    body = definition(library, docs[0]["passages"][0]["id"])
    response = manual_client.post("/api/v1/library/calibrations", json=body.model_dump())
    assert response.status_code == 202 and response.headers["cache-control"] == "no-store"
    for _ in body.cases:
        library.calibration.tick()
    report = manual_client.get("/api/v1/library/calibrations/" + response.json()["id"]).json()
    assert report["calibration"]["eligible"]
    assert any(
        w["id"] == "retrieval-calibration"
        for w in manual_client.get("/api/v1/workspace/health").json()["workers"]
    )
    for module in ("wiki", "reporter"):
        evidence = tool_call(manual_client, module, "retrieval_evaluation", evaluation_id=report["id"])
        assert evidence["calibration"]["validation"]["correct_accepts"] == 2
    assert (
        manual_client.post(
            "/api/v1/library/calibration-policy/document",
            json={"revision": 0, "enabled": True, "report_id": report["id"]},
        ).status_code
        == 200
    )
    response = manual_client.get("/api/v1/library/search?query=unsupported&kind=document&method=semantic")
    assert response.status_code == 200 and response.json()["calibration"]["abstained"]
    assert manual_client.get(
        "/api/v1/library/search?query=unsupported&kind=document&method=semantic&calibrated=false"
    ).json()["calibration"]["abstained"]
    snapshot = manual_client.post(
        "/api/v1/agents/ask",
        json={
            "module": "wiki",
            "message": "Find this evidence",
            "context": {
                "library_query": "unsupported",
                "library_source_type": "document",
                "library_search_method": "semantic",
            },
        },
    )
    assert snapshot.status_code == 200 and "withheld" in snapshot.json()["answer"].lower()
    response = manual_client.post(
        "/api/v1/agents/ask",
        json={
            "module": "wiki",
            "message": "Explain this cutoff",
            "context": {"retrieval_calibration_id": report["id"]},
        },
    )
    assert response.status_code == 200 and response.json()["tool"] == "retrieval_evaluation"
    assert manual_client.get("/api/v1/library/calibrations").headers["cache-control"] == "no-store"
    monkeypatch.setattr(library.calibration, "start", lambda *_: pytest.fail("Agent must not fit a cutoff"))
    status = tool_call(manual_client, "wiki", "research_search_status")
    assert status["calibration"]["document"]["state"] == "active"
    assert (
        manual_client.post(
            "/api/v1/library/calibration-policy/document", json={"revision": True, "enabled": False}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("provider", ["openai", "mistral"])
def test_hosted_calibration_uses_native_embedder_without_disclosing_credentials(hosted, provider):
    from test_hosted_embeddings import SECRET, build, setup
    from test_hosted_embeddings import sources as hosted_sources

    library, remote = hosted
    docs = hosted_sources(library)
    setup(library, provider)
    build(library)
    expected = docs[0]["passages"][0]["id"]
    body = definition(library, expected)
    # The independent hosted fixture maps no-source queries to an orthogonal
    # vector. One retained custody source keeps their leading cosine at zero.
    library.delete(docs[1]["id"])
    report = finish(library, body)
    assert report["calibration"]["eligible"]
    assert report["calibration"]["threshold"] == math.nextafter(0.0, math.inf)
    enable(library, report)
    found = library.search("custodian explanation", "document", 8, "semantic")
    assert found["items"][0]["id"] == expected
    assert not library.search("unsupported conclusion", "document", 8, "semantic")["items"]
    encoded = json.dumps({"report": report, "status": library.calibration.status(), "result": found})
    assert SECRET not in encoded and "research-embedding:" not in encoded
    assert report["snapshot"]["provider"] == provider
    calls = len(remote.calls)
    library.import_document("new.txt", b"Additional sources require explicit reindexing and calibration.")
    assert library.search("custodian", "document", 8, "semantic")["calibration"]["state"] == "stale"
    assert len(remote.calls) == calls


def test_admission_does_not_embed_and_each_worker_turn_is_one_query(semantic):
    library, server, docs = prepare(semantic)
    count = len(server.calls)
    item = library.calibration.start(definition(library, docs[0]["passages"][0]["id"]))
    assert len(server.calls) == count
    library.calibration.tick()
    assert library.calibration.get(item["id"])["completed"] == 1
    assert sum(path == "/api/embed" for _, path, _ in server.calls[count:]) == 1
    library.calibration.stop(item["id"])
    count = len(server.calls)
    library.calibration.tick()
    assert len(server.calls) == count


def test_new_routes_require_workspace_access(settings):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from sibyl.api.app import create_app

    settings.api_token = SecretStr("fixture-workspace-token")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/library/calibrations").status_code == 401
        assert (
            client.post(
                "/api/v1/library/calibration-policy/document", json={"revision": 0, "enabled": False}
            ).status_code
            == 401
        )
