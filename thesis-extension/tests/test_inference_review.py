#!/usr/bin/env python3
"""Offline tests for the suggestion review rules in sr8-mcp.

No Neo4j server, RL model or MCP runtime is needed: the Neo4j driver, the RL helpers
and (if it is not installed) the mcp package are replaced with fakes, so the tests
never write to the graph or to .rl-model.json.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import __future__
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

SR8_PATH = Path(__file__).resolve().parent.parent / "sr8-mcp"


def _load_sr8() -> types.ModuleType:
    try:
        import mcp.server.fastmcp  # noqa: F401
    except ImportError:
        fastmcp = types.ModuleType("mcp.server.fastmcp")

        class FastMCP:
            def __init__(self, *args, **kwargs):
                pass

            def tool(self, *args, **kwargs):
                return lambda fn: fn

            def run(self, *args, **kwargs):
                pass

        fastmcp.FastMCP = FastMCP
        sys.modules.update({
            "mcp": types.ModuleType("mcp"),
            "mcp.server": types.ModuleType("mcp.server"),
            "mcp.server.fastmcp": fastmcp,
        })
    module = types.ModuleType("sr8_mcp_under_test")
    module.__file__ = str(SR8_PATH)
    # Lazy annotations let the 3.10+ type hints in sr8-mcp load on Python 3.9.
    code = compile(SR8_PATH.read_text(encoding="utf-8"), str(SR8_PATH), "exec",
                   flags=__future__.annotations.compiler_flag, dont_inherit=True)
    exec(code, module.__dict__)
    return module


sr8 = _load_sr8()
# Kept before any test replaces them with recording fakes.
REAL_RL_UPDATE = sr8._rl_update
REAL_RL_ADJUST = sr8._rl_adjust_confidence


# ── Fake Neo4j driver ─────────────────────────────────────────────────────────

class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def single(self):
        return FakeRecord(self._rows[0]) if self._rows else None

    def __iter__(self):
        return iter(FakeRecord(r) for r in self._rows)


class FakeRecord(dict):
    def data(self):
        return dict(self)


EER_LABELS = ["ExtractedEssentialRequirement", "ExtractedRequirement", "Requirement"]
DEFAULT_SCHEMA = {  # relationships.csv rows: name -> (SourceLabel, TargetLabel)
    "suggestedProject": ("ExtractedEssentialRequirement", "Project"),
    "affectsRequirement": ("ChangeImpactReport", "Requirement"),
    "affectsProject": ("ChangeImpactReport", "Project"),
}
DEFAULT_SUBCLASS_OF = {  # SchemaLabel -[:SUBCLASS_OF*1..]-> ancestors
    "ExtractedEssentialRequirement": ["ExtractedRequirement", "Requirement"],
    "ExtractedRequirement": ["Requirement"],
}


class FakeGraph:
    """Answers queries by matching a distinctive substring; records every query run."""

    def __init__(self, assignments=None, suggestions=None, write_row=None, write_returns_nothing=False,
                 schema=None, subclass_of=None, requirement_labels=None, project_labels=None, candidates=None,
                 target=None):
        self.assignments = assignments if assignments is not None else [
            {"assigned_project": None, "source": None}
        ]
        self.suggestions = suggestions or []
        self.write_row = write_row or {"req_id": "REQ-1", "project_id": "SRP8-045",
                                       "revision_count": None, "already_assigned": False}
        self.write_returns_nothing = write_returns_nothing
        # Same-ADR candidates for _similar_assigned_requirements: dicts with req_id, req_name,
        # clause and assigned_projects. target is (requirementName, clauseNumber) of the requirement.
        self.candidates = candidates or []
        self.target = target or ("Brake Linings", "5.1.1.3")
        self.schema = DEFAULT_SCHEMA if schema is None else schema
        self.subclass_of = DEFAULT_SUBCLASS_OF if subclass_of is None else subclass_of
        self.requirement_labels = requirement_labels or EER_LABELS
        self.project_labels = project_labels or ["Project"]
        self.queries = []
        self.commits = 0

    def run(self, query, **params):
        self.queries.append((query, params))
        if "AS target_clause" in query:
            base = {"target_name": self.target[0], "target_clause": self.target[1], "adr_id": "ADR-31"}
            if not self.candidates:
                return FakeResult([dict(base, req_id=None, req_name=None, clause=None,
                                        is_applicable=None, assigned_projects=[])])
            return FakeResult([dict(base, is_applicable=True, **c) for c in self.candidates])
        if "AS assigned_project" in query:
            return FakeResult([dict({"source_labels": self.requirement_labels,
                                     "target_labels": self.project_labels}, **row) for row in self.assignments])
        if "count(s) AS total" in query:
            return FakeResult([{"total": len(self.schema)}])
        if "r.sourceLabel AS source_label" in query:
            declared = self.schema.get(params["rel_type"])
            return FakeResult([{"source_label": declared[0], "target_label": declared[1]}] if declared else [])
        if "AS ancestors" in query:
            found = {a for label in params["labels"] for a in self.subclass_of.get(label, [])}
            return FakeResult([{"ancestors": sorted(found)}])
        if "MATCH (r:ExtractedEssentialRequirement {hasID: id})" in query:
            return FakeResult([{"labels": self.requirement_labels}] if params["ids"] else [])
        if "MATCH (p:Project {projectID: id})" in query:
            return FakeResult([{"labels": self.project_labels}] if params["ids"] else [])
        if "s.rejectionReason AS rejection_reason" in query:
            return FakeResult(self.suggestions)
        if ("rel.previousConfidence" in query or "CREATE (r)-[rel:suggestedProject]" in query
                or "count(existing)" in query or "suggested.rejectionReason" in query
                or "suggested.modifiedTo" in query):
            return FakeResult([] if self.write_returns_nothing else [self.write_row])
        return FakeResult([])

    def ran(self, fragment):
        return [(q, p) for q, p in self.queries if fragment in q]


class FakeTx:
    def __init__(self, graph):
        self.graph = graph

    def run(self, query, **params):
        return self.graph.run(query, **params)

    def commit(self):
        self.graph.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession(FakeTx):
    def begin_transaction(self):
        return FakeTx(self.graph)


class FakeDriver:
    def __init__(self, graph):
        self.graph = graph

    def session(self, **kwargs):
        return FakeSession(self.graph)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def reviewed(status, by="bob", at="2026-10-01T10:00:00Z", reason=None, inferred_at="T-REVIEWED", confidence=0.7):
    return {"status": status, "confidence": confidence, "inference_state": "inference_weak_yes_mid",
            "rl_action": "keep_confidence", "inferred_at": inferred_at, "reviewed_by": by, "reviewed_at": at,
            "rejection_reason": reason}


def pending(confidence=0.5, state="inference_weak_yes_mid", rl_action="increase_confidence"):
    return {"status": None, "confidence": confidence, "inference_state": state, "rl_action": rl_action,
            "inferred_at": "T-PENDING", "reviewed_by": None, "reviewed_at": None, "rejection_reason": None}


class Base(unittest.TestCase):
    def use(self, graph):
        self.graph = graph
        self.rl_updates = []
        self.rl_adjust_calls = []
        log_dir = tempfile.TemporaryDirectory()
        self.addCleanup(log_dir.cleanup)
        self.inference_log = Path(log_dir.name) / "inference.jsonl"
        sr8._INFERENCE_LOG_PATH = self.inference_log
        sr8._neo4j_driver = lambda: FakeDriver(graph)
        def record_update(reward, state, rl_action):
            self.rl_updates.append((reward, state, rl_action))
            return True

        sr8._rl_update = record_update

        def adjust(base, state):
            self.rl_adjust_calls.append((base, state))
            return base, "keep_confidence"

        sr8._rl_adjust_confidence = adjust
        return graph

    def no_suggestion_written(self):
        self.assertEqual(self.graph.ran("rel.previousConfidence"), [])
        self.assertEqual(self.graph.ran("CREATE (r)-[rel:suggestedProject]"), [])
        self.assertEqual(self.graph.ran("MERGE (r)-[rel:suggestedProject]"), [])


# ── 1a–1d: write_inferred_project_link ────────────────────────────────────────

class WriteInferredLinkTests(Base):
    def call(self, **kwargs):
        args = {"requirement_id": "REQ-1", "project_id": "SRP8-045", "confidence": 0.65, "reasoning": "same ADR"}
        args.update(kwargs)
        return json.loads(sr8.write_inferred_project_link(**args))

    def test_1a_already_assigned_to_same_project_is_not_written(self):
        self.use(FakeGraph(assignments=[{"assigned_project": "SRP8-045", "source": "extracted"}]))
        out = self.call()
        self.assertEqual(out["status"], "already_assigned")
        self.assertEqual(out["source"], "extracted")
        self.no_suggestion_written()
        self.assertEqual(self.rl_adjust_calls, [])

    def test_1b_reviewed_suggestion_returns_earlier_decision_and_is_untouched(self):
        self.use(FakeGraph(suggestions=[reviewed("rejected", reason="wrong subsystem")]))
        out = self.call()
        self.assertEqual(out["status"], "previously_reviewed")
        self.assertEqual(out["previous_decision"], {
            "status": "rejected", "reviewed_by": "bob",
            "reviewed_at": "2026-10-01T10:00:00Z", "rejection_reason": "wrong subsystem",
        })
        self.no_suggestion_written()
        self.assertEqual(self.graph.commits, 0)
        self.assertEqual(self.rl_adjust_calls, [])

    def test_1b_latest_of_several_reviews_is_returned(self):
        self.use(FakeGraph(suggestions=[
            reviewed("rejected", at="2026-10-01T10:00:00Z"),
            reviewed("promoted", by="carol", at="2026-10-05T09:00:00Z"),
        ]))
        out = self.call()
        self.assertEqual(out["previous_decision"]["status"], "promoted")
        self.assertEqual(out["previous_decision"]["reviewed_by"], "carol")

    def test_1b_resubmit_creates_a_second_edge_and_never_merges(self):
        self.use(FakeGraph(suggestions=[reviewed("rejected", inferred_at="T-OLD")]))
        out = self.call(resubmit=True)
        self.assertEqual(out["status"], "written")
        self.assertEqual(out["write_mode"], "resubmitted")
        creates = self.graph.ran("CREATE (r)-[rel:suggestedProject]")
        self.assertEqual(len(creates), 1)
        query, params = creates[0]
        self.assertEqual(params["resubmission_of"], "T-OLD")
        self.assertIn("rel.resubmissionOf = $resubmission_of", query)
        self.assertNotIn("MERGE", query)
        self.assertEqual(self.graph.ran("rel.previousConfidence"), [])
        self.assertEqual(self.graph.commits, 1)

    def test_1c_pending_suggestion_is_revised_in_place_keeping_previous_values(self):
        self.use(FakeGraph(suggestions=[pending(confidence=0.5)],
                           write_row={"req_id": "REQ-1", "project_id": "SRP8-045", "revision_count": 1}))
        out = self.call(confidence=0.7)
        self.assertEqual(out["write_mode"], "revised")
        self.assertEqual(out["revision_count"], 1)
        updates = self.graph.ran("rel.previousConfidence")
        self.assertEqual(len(updates), 1)
        query, params = updates[0]
        self.assertIn("WHERE rel.status IS NULL", query)
        self.assertIn("rel.previousReasoning  = rel.reasoning", query)
        self.assertIn("coalesce(rel.revisionCount, 0) + 1", query)
        # previous values are saved in a SET clause that runs before the one writing new values
        self.assertLess(query.index("rel.previousConfidence"), query.index("rel.confidence     = $confidence"))
        self.assertEqual(params["confidence"], 0.7)
        self.assertEqual(self.graph.ran("CREATE (r)-[rel:suggestedProject]"), [])

    def test_1c_pending_wins_over_resubmit_when_both_exist(self):
        self.use(FakeGraph(suggestions=[reviewed("rejected"), pending()]))
        out = self.call(resubmit=True)
        self.assertEqual(out["write_mode"], "revised")
        self.assertEqual(self.graph.ran("CREATE (r)-[rel:suggestedProject]"), [])

    def test_1d_assigned_to_other_project_still_writes_with_warning(self):
        self.use(FakeGraph(assignments=[{"assigned_project": "SRP8-046", "source": "extracted"}]))
        out = self.call()
        self.assertEqual(out["status"], "written")
        self.assertEqual(out["write_mode"], "created")
        self.assertIn("SRP8-046", out["warning"])
        self.assertEqual(len(self.graph.ran("CREATE (r)-[rel:suggestedProject]")), 1)

    def test_new_suggestion_has_no_warning(self):
        self.use(FakeGraph())
        out = self.call()
        self.assertEqual(out["write_mode"], "created")
        self.assertIsNone(out["warning"])
        self.assertIsNone(out["resubmission_of"])

    def test_missing_requirement_or_project(self):
        self.use(FakeGraph(assignments=[]))
        out = self.call()
        self.assertEqual(out["error"], "Requirement or Project not found.")
        self.no_suggestion_written()


# ── 2: no double-counted feedback ────────────────────────────────────────────

class FeedbackTests(Base):
    def test_2_record_feedback_refused_after_review(self):
        self.use(FakeGraph(suggestions=[reviewed("rejected", reason="wrong subsystem")]))
        out = json.loads(sr8.record_feedback("REQ-1", "SRP8-045", "rejected", -1.0))
        self.assertIn("already reviewed", out["error"])
        self.assertEqual(out["previous_decision"]["status"], "rejected")
        self.assertEqual(self.graph.ran("MERGE (fe:FeedbackEvent"), [])
        self.assertEqual(self.graph.commits, 0)
        self.assertEqual(self.rl_updates, [])

    def test_2_record_feedback_refused_without_any_suggestion(self):
        self.use(FakeGraph(suggestions=[]))
        out = json.loads(sr8.record_feedback("REQ-1", "SRP8-045", "confirmed", 1.0))
        self.assertIn("No suggestedProject relationship", out["error"])
        self.assertNotIn("previous_decision", out)
        self.assertEqual(self.graph.ran("MERGE (fe:FeedbackEvent"), [])
        self.assertEqual(self.rl_updates, [])

    def test_2_feedback_uses_only_the_pending_suggestion(self):
        # Reviewed edge has confidence 0.95; pending edge has 0.5, so no overconfidence penalty.
        self.use(FakeGraph(suggestions=[reviewed("rejected", confidence=0.95), pending(confidence=0.5)]))
        out = json.loads(sr8.record_feedback("REQ-1", "SRP8-045", "rejected", -1.0))
        self.assertEqual(out["reward_applied"], -1.0)
        self.assertFalse(out["overconfidence_penalty_applied"])
        self.assertEqual(len(self.graph.ran("MERGE (fe:FeedbackEvent")), 1)

    def test_2_promote_refused_after_review_returns_earlier_decision(self):
        self.use(FakeGraph(suggestions=[reviewed("promoted", by="carol")]))
        out = json.loads(sr8.promote_inferred_link("REQ-1", "SRP8-045", "alice"))
        self.assertEqual(out["previous_decision"]["reviewed_by"], "carol")
        self.assertEqual(self.graph.ran("count(existing)"), [])
        self.assertEqual(self.graph.ran("MERGE (fe:FeedbackEvent"), [])
        self.assertEqual(self.rl_updates, [])

    def test_reject_keeps_suggestion_records_reviewer_and_then_refuses_second_feedback(self):
        graph = self.use(FakeGraph(suggestions=[pending(confidence=0.92, state="inference_weak_no_high")]))
        out = json.loads(sr8.reject_inferred_link("REQ-1", "SRP8-045", "bob", "wrong subsystem"))
        self.assertEqual(out["status"], "rejected")
        self.assertEqual(out["feedback"]["reward_applied"], -2.0)
        fe_params = graph.ran("MERGE (fe:FeedbackEvent")[0][1]
        self.assertEqual(fe_params["reviewer"], "bob")
        reject_query, reject_params = graph.ran("suggested.rejectionReason")[0]
        self.assertIn("WHERE suggested.status IS NULL", reject_query)
        self.assertEqual(reject_params["reason"], "wrong subsystem")
        self.assertFalse(any("DELETE" in q for q, _ in graph.queries))
        self.assertEqual(self.rl_updates, [(-2.0, "inference_weak_no_high", "increase_confidence")])

        # The graph now holds the rejected suggestion; a second feedback call is refused.
        graph.suggestions = [reviewed("rejected", reason="wrong subsystem", confidence=0.92)]
        again = json.loads(sr8.record_feedback("REQ-1", "SRP8-045", "rejected", -1.0))
        self.assertIn("already reviewed", again["error"])
        self.assertEqual(len(graph.ran("MERGE (fe:FeedbackEvent")), 1)
        self.assertEqual(len(self.rl_updates), 1)

    def test_promote_acts_only_on_pending_edge(self):
        graph = self.use(FakeGraph(suggestions=[reviewed("rejected"), pending()]))
        out = json.loads(sr8.promote_inferred_link("REQ-1", "SRP8-045", "alice"))
        self.assertEqual(out["status"], "promoted")
        promote_query = graph.ran("count(existing)")[0][0]
        self.assertIn("WHERE suggested.status IS NULL", promote_query)
        self.assertEqual(graph.commits, 1)



# ── modify_inferred_link ─────────────────────────────────────────────────────

class ModifyTests(Base):
    def test_modify_assigns_other_project_and_marks_suggestion_modified(self):
        graph = self.use(FakeGraph(suggestions=[pending(confidence=0.6)],
                                   write_row={"req_id": "REQ-1", "project_id": "SRP8-046", "already_assigned": False}))
        out = json.loads(sr8.modify_inferred_link("REQ-1", "SRP8-045", "SRP8-046", "alice", "rear axle"))
        self.assertEqual(out["status"], "modified")
        self.assertEqual(out["project_id"], "SRP8-046")
        self.assertEqual(out["feedback"]["reward_applied"], 0.5)
        fe_params = graph.ran("MERGE (fe:FeedbackEvent")[0][1]
        self.assertEqual((fe_params["action"], fe_params["reviewer"], fe_params["proj_id"]), ("modified", "alice", "SRP8-045"))
        query, params = graph.ran("suggested.modifiedTo")[0]
        self.assertIn("WHERE suggested.status IS NULL", query)
        self.assertIn("confirmed.source                 = 'inferred-modified'", query)
        self.assertIn("suggested.status             = 'modified'", query)
        self.assertEqual(params["new_project_id"], "SRP8-046")
        self.assertFalse(any("DELETE" in q for q, _ in graph.queries))
        self.assertEqual(graph.commits, 1)
        self.assertEqual(self.rl_updates, [(0.5, "inference_weak_yes_mid", "increase_confidence")])

    def test_modify_to_same_project_is_refused(self):
        graph = self.use(FakeGraph(suggestions=[pending()]))
        out = json.loads(sr8.modify_inferred_link("REQ-1", "SRP8-045", "SRP8-045", "alice"))
        self.assertIn("confirm the suggestion instead", out["error"])
        self.assertEqual(graph.queries, [])

    def test_modify_to_unknown_project_rolls_back(self):
        graph = self.use(FakeGraph(suggestions=[pending()], write_returns_nothing=True))
        out = json.loads(sr8.modify_inferred_link("REQ-1", "SRP8-045", "NOPE", "alice"))
        self.assertIn("not found", out["error"])
        self.assertEqual(graph.commits, 0)
        self.assertEqual(self.rl_updates, [])

    def test_modify_refused_after_review(self):
        graph = self.use(FakeGraph(suggestions=[reviewed("rejected")]))
        out = json.loads(sr8.modify_inferred_link("REQ-1", "SRP8-045", "SRP8-046", "alice"))
        self.assertEqual(out["previous_decision"]["status"], "rejected")
        self.assertEqual(graph.ran("suggested.modifiedTo"), [])



# ── Schema-layer validation ──────────────────────────────────────────────────

class SchemaValidationTests(Base):
    def validate(self, graph, rel_type, source, target):
        return sr8._validate_against_schema(rel_type, source, target, tx=FakeTx(graph))

    def test_allowed_pair_passes(self):
        ok, reason = self.validate(FakeGraph(), "suggestedProject", EER_LABELS, ["Project"])
        self.assertTrue(ok, reason)
        self.assertIn("declared in schema", reason)

    def test_declared_label_matches_through_subclass_ancestor(self):
        # affectsRequirement targets Requirement; the node only carries the subclass label.
        ok, reason = self.validate(FakeGraph(), "affectsRequirement", ["ChangeImpactReport"],
                                   ["ExtractedEssentialRequirement"])
        self.assertTrue(ok, reason)
        self.assertIn("target matches Requirement", reason)

    def test_wrong_target_label_is_refused(self):
        ok, reason = self.validate(FakeGraph(), "suggestedProject", EER_LABELS, ["Department"])
        self.assertFalse(ok)
        self.assertIn("requires target label Project", reason)

    def test_wrong_source_label_is_refused(self):
        ok, reason = self.validate(FakeGraph(), "suggestedProject", ["Component"], ["Project"])
        self.assertFalse(ok)
        self.assertIn("requires source label", reason)

    def test_empty_schema_is_refused(self):
        ok, reason = self.validate(FakeGraph(schema={}), "suggestedProject", EER_LABELS, ["Project"])
        self.assertFalse(ok)
        self.assertIn("Schema layer is not loaded", reason)

    def test_undeclared_relationship_is_refused(self):
        ok, reason = self.validate(FakeGraph(), "inventedRelation", EER_LABELS, ["Project"])
        self.assertFalse(ok)
        self.assertIn("not declared", reason)

    def test_alternatives_and_all_wildcard(self):
        graph = FakeGraph(schema={"interface": ("System|Subsystem", "System|Subsystem"),
                                  "documentedIn": ("All", "Document")})
        self.assertTrue(self.validate(graph, "interface", ["Subsystem"], ["System"])[0])
        self.assertTrue(self.validate(graph, "documentedIn", ["Anything"], ["Document"])[0])
        self.assertFalse(self.validate(graph, "documentedIn", ["Anything"], ["Project"])[0])

    # write_inferred_project_link

    def call_write(self):
        return json.loads(sr8.write_inferred_project_link("REQ-1", "SRP8-045", 0.65, "same ADR"))

    def test_write_records_schema_validation_on_edge_and_response(self):
        graph = self.use(FakeGraph())
        out = self.call_write()
        self.assertTrue(out["schema_validation"]["ok"])
        query, _ = graph.ran("CREATE (r)-[rel:suggestedProject]")[0]
        self.assertIn("rel.schemaValidated = true", query)
        self.assertIn("rel.schemaCheckedAt = datetime()", query)

    def test_revision_also_records_schema_validation(self):
        graph = self.use(FakeGraph(suggestions=[pending()]))
        self.call_write()
        self.assertIn("rel.schemaValidated = true", graph.ran("rel.previousConfidence")[0][0])

    def test_write_refused_for_wrong_target_label(self):
        graph = self.use(FakeGraph(project_labels=["Department"]))
        out = self.call_write()
        self.assertIn("Schema validation failed", out["error"])
        self.assertFalse(out["schema_validation"]["ok"])
        self.no_suggestion_written()
        self.assertEqual(self.rl_adjust_calls, [])
        self.assertEqual(graph.commits, 0)

    def test_write_refused_when_schema_not_loaded(self):
        self.use(FakeGraph(schema={}))
        out = self.call_write()
        self.assertIn("Schema layer is not loaded", out["error"])
        self.no_suggestion_written()

    # write_change_impact_report

    def call_cir(self, reqs=("REQ-1",), projs=("SRP8-045",)):
        return json.loads(sr8.write_change_impact_report("wheel diameter change", list(reqs), list(projs), "medium"))

    def test_change_impact_report_validates_both_relationship_types(self):
        graph = self.use(FakeGraph())
        out = self.call_cir()
        self.assertEqual(out["status"], "created")
        self.assertTrue(out["schema_validation"]["affectsRequirement"]["ok"])
        self.assertTrue(out["schema_validation"]["affectsProject"]["ok"])
        self.assertEqual(len(graph.ran("MERGE (cir:ChangeImpactReport")), 1)
        self.assertEqual(graph.commits, 1)

    def test_change_impact_report_refused_when_schema_not_loaded(self):
        graph = self.use(FakeGraph(schema={}))
        out = self.call_cir()
        self.assertIn("Schema layer is not loaded", out["error"])
        self.assertEqual(graph.ran("MERGE (cir:ChangeImpactReport"), [])
        self.assertEqual(graph.ran("MERGE (cir)-["), [])
        self.assertEqual(graph.commits, 0)

    def test_change_impact_report_refused_for_wrong_target_label(self):
        graph = self.use(FakeGraph(project_labels=["Department"]))
        out = self.call_cir()
        self.assertFalse(out["schema_validation"]["affectsProject"]["ok"])
        self.assertEqual(graph.ran("MERGE (cir:ChangeImpactReport"), [])
        self.assertEqual(graph.commits, 0)

    def test_change_impact_report_without_links_needs_no_schema(self):
        graph = self.use(FakeGraph(schema={}))
        out = self.call_cir(reqs=(), projs=())
        self.assertEqual(out["status"], "created")
        self.assertEqual(out["schema_validation"], {})
        self.assertEqual(graph.commits, 1)



# ── Problem B: credit the stored action; independent state features ───────────

class RlCreditTests(Base):
    def test_write_stores_chosen_action_and_base_confidence(self):
        graph = self.use(FakeGraph())
        sr8._rl_adjust_confidence = lambda base, state: (round(base - 0.1, 10), "decrease_confidence")
        out = json.loads(sr8.write_inferred_project_link("REQ-1", "SRP8-045", 0.65, "same ADR"))
        self.assertEqual((out["rl_action"], out["original_confidence"], out["adjusted_confidence"]),
                         ("decrease_confidence", 0.65, 0.55))
        query, params = graph.ran("CREATE (r)-[rel:suggestedProject]")[0]
        self.assertIn("rel.rlAction       = $rl_action", query)
        self.assertIn("rel.baseConfidence = $base_confidence", query)
        self.assertEqual((params["rl_action"], params["base_confidence"], params["confidence"]),
                         ("decrease_confidence", 0.65, 0.55))

    def test_revision_stores_new_action_and_base_confidence(self):
        graph = self.use(FakeGraph(suggestions=[pending()]))
        sr8.write_inferred_project_link("REQ-1", "SRP8-045", 0.65, "same ADR")
        query, params = graph.ran("rel.previousConfidence")[0]
        self.assertIn("rel.rlAction       = $rl_action", query)
        self.assertEqual((params["rl_action"], params["base_confidence"]), ("keep_confidence", 0.65))

    def test_inference_state_uses_the_uncapped_candidate_set(self):
        # 7 same-ADR assigned requirements (more than the 5 the tool displays), none on SRP8-045.
        others = [{"req_id": f"REQ-31-{i:03d}", "req_name": f"Rule {i}", "clause": f"5.{i}",
                   "assigned_projects": ["SRP8-046"]} for i in range(10, 17)]
        graph = self.use(FakeGraph(candidates=others))
        out = json.loads(sr8.write_inferred_project_link("REQ-1", "SRP8-045", 0.65, "same ADR"))
        self.assertEqual(out["same_adr_assigned"], 7)
        self.assertFalse(out["project_has_same_adr"])
        self.assertEqual(out["inference_state"], "inference_strong_no_mid")
        self.assertEqual(graph.ran("AS target_clause")[0][1]["req_id"], "REQ-1")

    def test_project_feature_comes_from_the_candidates_assigned_projects(self):
        graph = self.use(FakeGraph(candidates=[{"req_id": "REQ-31-006", "req_name": "Brake Linings",
                                                "clause": "5.1.1.3", "assigned_projects": ["SRP8-045"]}]))
        out = json.loads(sr8.write_inferred_project_link("REQ-1", "SRP8-045", 0.65, "same ADR"))
        self.assertEqual(out["inference_state"], "inference_weak_yes_mid")

    def test_rejection_credits_the_stored_action_not_a_mapped_one(self):
        # The agent had chosen to INCREASE confidence; the rejection must penalise that action.
        self.use(FakeGraph(suggestions=[pending(rl_action="increase_confidence")]))
        out = json.loads(sr8.reject_inferred_link("REQ-1", "SRP8-045", "bob", "wrong"))
        self.assertEqual(self.rl_updates, [(-1.0, "inference_weak_yes_mid", "increase_confidence")])
        self.assertEqual(out["feedback"]["rl_action"], "increase_confidence")

    def test_confirmation_credits_the_stored_action_even_if_it_was_decrease(self):
        self.use(FakeGraph(suggestions=[pending(rl_action="decrease_confidence")]))
        sr8.promote_inferred_link("REQ-1", "SRP8-045", "alice")
        self.assertEqual(self.rl_updates, [(1.0, "inference_weak_yes_mid", "decrease_confidence")])

    def test_feedback_event_records_the_credited_action(self):
        graph = self.use(FakeGraph(suggestions=[pending(rl_action="keep_confidence")]))
        sr8.reject_inferred_link("REQ-1", "SRP8-045", "bob", "wrong")
        self.assertEqual(graph.ran("MERGE (fe:FeedbackEvent")[0][1]["rl_action"], "keep_confidence")

    def test_overconfidence_penalty_kept(self):
        self.use(FakeGraph(suggestions=[pending(confidence=0.85)]))
        out = json.loads(sr8.reject_inferred_link("REQ-1", "SRP8-045", "bob", "wrong"))
        self.assertEqual(out["feedback"]["reward_applied"], -2.0)
        self.assertEqual(sr8.PENALTY_OVERCONFIDENT, -2.0)

    def test_no_feedback_mapping_table_remains(self):
        self.assertNotIn("rl_map", SR8_PATH.read_text(encoding="utf-8"))

    def test_legacy_suggestion_without_stored_action_does_not_update_q(self):
        self.assertFalse(REAL_RL_UPDATE(-1.0, "inference_weak_no_low", None))
        self.assertFalse(REAL_RL_UPDATE(-1.0, None, "keep_confidence"))

    def test_adjust_returns_the_chosen_action_and_clamps(self):
        class FakeAgent:
            def __init__(self, action):
                self.action = action

            def choose_action(self, state, actions):
                return self.action

        saved = sr8._load_rl_agent
        try:
            sr8._load_rl_agent = lambda: FakeAgent("decrease_confidence")
            self.assertEqual(REAL_RL_ADJUST(0.05, "inference_weak_no_low"), (0.0, "decrease_confidence"))
            sr8._load_rl_agent = lambda: FakeAgent("increase_confidence")
            self.assertEqual(REAL_RL_ADJUST(0.95, "inference_strong_yes_high"), (1.0, "increase_confidence"))
            sr8._load_rl_agent = lambda: None
            self.assertEqual(REAL_RL_ADJUST(0.5, "inference_weak_no_mid"), (0.5, None))
        finally:
            sr8._load_rl_agent = saved


class InferenceStateTests(unittest.TestCase):
    def test_band_boundaries_come_from_one_constant(self):
        self.assertEqual(sr8.CONFIDENCE_BANDS, (("high", 0.7), ("mid", 0.4)))
        cases = {0.71: "high", 0.7: "mid", 0.41: "mid", 0.4: "low", 0.0: "low", 1.0: "high"}
        for confidence, band in cases.items():
            self.assertEqual(sr8._confidence_band(confidence), band, confidence)

    def test_all_four_evidence_project_combinations_are_reachable(self):
        self.assertEqual(sr8._inference_state(5, True, 0.8), "inference_strong_yes_high")
        self.assertEqual(sr8._inference_state(5, False, 0.8), "inference_strong_no_high")   # assigned elsewhere
        self.assertEqual(sr8._inference_state(1, True, 0.5), "inference_weak_yes_mid")
        self.assertEqual(sr8._inference_state(0, False, 0.3), "inference_weak_no_low")
        self.assertEqual(sr8._inference_state(2, False, 0.3), "inference_weak_no_low")
        self.assertEqual(sr8._inference_state(3, False, 0.3), "inference_strong_no_low")    # threshold is >= 3

    def test_twelve_states(self):
        produced = {sr8._inference_state(n, p, c) for n in (0, 3) for p in (True, False) for c in (0.9, 0.5, 0.1)}
        self.assertEqual(produced, set(sr8._INFERENCE_STATES))
        self.assertEqual(len(produced), 12)



# ── logs/inference.jsonl ─────────────────────────────────────────────────────

class InferenceLogTests(Base):
    def lines(self):
        return [json.loads(line) for line in self.inference_log.read_text(encoding="utf-8").splitlines()]

    def test_suggestion_write_is_logged(self):
        self.use(FakeGraph())
        sr8._rl_adjust_confidence = lambda base, state: (0.75, "increase_confidence")
        sr8.write_inferred_project_link("REQ-1", "SRP8-045", 0.65, "same ADR")
        [line] = self.lines()
        self.assertEqual((line["event"], line["outcome"], line["write_mode"]), ("suggest", "written", "created"))
        self.assertEqual((line["requirement_id"], line["project_id"]), ("REQ-1", "SRP8-045"))
        self.assertEqual((line["base_confidence"], line["adjusted_confidence"]), (0.65, 0.75))
        self.assertEqual((line["inference_state"], line["rl_action"]), ("inference_weak_no_mid", "increase_confidence"))
        self.assertTrue(line["schema_validation"]["ok"])
        self.assertIsNone(line["reviewer"])

    def test_refused_write_is_logged_with_schema_result(self):
        self.use(FakeGraph(schema={}))
        sr8.write_inferred_project_link("REQ-1", "SRP8-045", 0.65, "same ADR")
        [line] = self.lines()
        self.assertEqual(line["outcome"], "error")
        self.assertFalse(line["schema_validation"]["ok"])
        self.assertEqual(line["base_confidence"], 0.65)

    def test_review_event_is_logged_with_reward_reviewer_and_confidences(self):
        suggestion = dict(pending(confidence=0.85, state="inference_weak_no_high", rl_action="keep_confidence"),
                          base_confidence=0.85, schema_validated=True)
        self.use(FakeGraph(suggestions=[suggestion]))
        sr8.reject_inferred_link("REQ-1", "SRP8-045", "bob", "wrong subsystem")
        [line] = self.lines()
        self.assertEqual((line["event"], line["outcome"], line["reviewer"], line["reason"]),
                         ("reject", "rejected", "bob", "wrong subsystem"))
        self.assertEqual((line["reward"], line["overconfidence_penalty_applied"]), (-2.0, True))
        self.assertEqual((line["base_confidence"], line["adjusted_confidence"]), (0.85, 0.85))
        self.assertEqual((line["inference_state"], line["rl_action"]), ("inference_weak_no_high", "keep_confidence"))
        self.assertEqual(line["schema_validation"], {"stored_on_suggestion": True})

    def test_refused_review_is_logged_with_previous_decision(self):
        self.use(FakeGraph(suggestions=[reviewed("rejected")]))
        sr8.promote_inferred_link("REQ-1", "SRP8-045", "alice")
        [line] = self.lines()
        self.assertEqual((line["event"], line["outcome"], line["reviewer"]), ("promote", "error", "alice"))
        self.assertEqual(line["previous_decision"]["status"], "rejected")

    def test_modify_logs_both_projects(self):
        self.use(FakeGraph(suggestions=[pending()],
                           write_row={"req_id": "REQ-1", "project_id": "SRP8-046", "already_assigned": False}))
        sr8.modify_inferred_link("REQ-1", "SRP8-045", "SRP8-046", "alice", "rear axle")
        [line] = self.lines()
        self.assertEqual((line["project_id"], line["new_project_id"], line["reward"]), ("SRP8-045", "SRP8-046", 0.5))

    def test_log_is_append_only(self):
        self.use(FakeGraph())
        for _ in range(3):
            sr8.write_inferred_project_link("REQ-1", "SRP8-045", 0.65, "same ADR")
        self.assertEqual(len(self.lines()), 3)


if __name__ == "__main__":
    unittest.main()
