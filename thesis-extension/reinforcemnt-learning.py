"""Extended reinforcement learning helper for thesis-extension.

This file keeps the exact user-requested name: reinforcemnt-learning.py.

It provides a more complete tabular Q-learning toolkit with:
- epsilon-greedy exploration
- optional experience replay
- training/evaluation helpers
- policy export
- JSON persistence
- built-in self-tests

Two separate learning problems share one model file (.rl-model.json, schema version 3):

- Problem A, "problem_a": retrieval-strategy selection in ollama-mcp
  (state adr_lookup; actions graph_first / documents_first / hybrid). Multi-step
  Q-learning config (discount_factor 0.9). No synthetic prior: it learns only from live
  turns. general_lookup has a single action, so ollama-mcp does not update it.
- Problem B, "problem_b": inference-confidence adjustment in sr8-mcp
  (12 states inference_<strong|weak>_<yes|no>_<high|mid|low>; actions
  increase_confidence / keep_confidence / decrease_confidence). Each suggestion is a
  one-step decision, so its config has discount_factor 0.0 and the update reduces to
  Q <- Q + alpha * (r - Q).

Each problem has its own config (epsilon, alpha, gamma), Q-table and episode_rewards, so
exploration decay in one never affects the other. Version 2 files (one shared agent) are
migrated on read; see migrate_model_document.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, asdict
import fcntl
import json
import os
import random
from pathlib import Path
from typing import Callable, Deque, Dict, Iterable, List, Tuple


State = str
Action = str


@dataclass
class RLConfig:
    learning_rate: float = 0.2
    discount_factor: float = 0.9
    exploration_rate: float = 0.15
    min_exploration_rate: float = 0.02
    exploration_decay: float = 0.995
    optimistic_initial_q: float = 0.0


PROBLEM_A = "problem_a"  # retrieval-strategy selection (ollama-mcp)
PROBLEM_B = "problem_b"  # inference-confidence adjustment (sr8-mcp)
PROBLEMS = (PROBLEM_A, PROBLEM_B)
MODEL_SCHEMA_VERSION = 3


def retrieval_config() -> RLConfig:
    """Problem A: multi-step Q-learning (unchanged defaults)."""
    return RLConfig()


def inference_config() -> RLConfig:
    """Problem B: single-step decisions, so no bootstrapping: Q <- Q + alpha * (r - Q)."""
    return RLConfig(discount_factor=0.0)


def default_config(problem: str) -> RLConfig:
    if problem == PROBLEM_A:
        return retrieval_config()
    if problem == PROBLEM_B:
        return inference_config()
    raise ValueError(f"unknown problem {problem!r}; expected one of {PROBLEMS}")


INFERENCE_STATES: List[State] = [
    f"inference_{ev}_{pop}_{cb}"
    for ev in ("strong", "weak")
    for pop in ("yes", "no")
    for cb in ("high", "mid", "low")
]
INFERENCE_ACTIONS: List[Action] = [
    "increase_confidence",
    "keep_confidence",
    "decrease_confidence",
]


@dataclass
class Transition:
    state: State
    action: Action
    reward: float
    next_state: State
    next_actions: List[Action]


class ReplayBuffer:
    def __init__(self, capacity: int = 2000) -> None:
        self.capacity = capacity
        self._buffer: Deque[Transition] = deque(maxlen=capacity)

    def push(self, item: Transition) -> None:
        self._buffer.append(item)

    def sample(self, batch_size: int) -> List[Transition]:
        batch_size = min(batch_size, len(self._buffer))
        if batch_size <= 0:
            return []
        return random.sample(list(self._buffer), batch_size)

    def __len__(self) -> int:
        return len(self._buffer)


class QLearningAgent:
    """Tabular Q-learning agent with optional replay updates."""

    def __init__(self, config: RLConfig | None = None) -> None:
        self.config = config or RLConfig()
        self.q_table: Dict[State, Dict[Action, float]] = {}
        self.episode_rewards: List[float] = []

    def choose_action(self, state: State, actions: List[Action]) -> Action:
        if not actions:
            raise ValueError("actions cannot be empty")
        self._ensure_state_actions(state, actions)

        if random.random() < self.config.exploration_rate:
            return random.choice(actions)

        return self.greedy_action(state, actions)

    def greedy_action(self, state: State, actions: List[Action]) -> Action:
        if not actions:
            raise ValueError("actions cannot be empty")
        self._ensure_state_actions(state, actions)
        state_scores = self.q_table[state]
        max_q = max(state_scores[a] for a in actions)
        candidates = [a for a in actions if state_scores[a] == max_q]
        return random.choice(candidates)

    def q_value(self, state: State, action: Action) -> float:
        self._ensure_state_actions(state, [action])
        return self.q_table[state][action]

    def update(self, transition: Transition) -> float:
        self._ensure_state_actions(transition.state, [transition.action])
        self._ensure_state_actions(transition.next_state, transition.next_actions)

        current_q = self.q_table[transition.state][transition.action]
        next_max_q = (
            max(self.q_table[transition.next_state][a] for a in transition.next_actions)
            if transition.next_actions
            else 0.0
        )

        td_target = transition.reward + self.config.discount_factor * next_max_q
        td_error = td_target - current_q
        self.q_table[transition.state][transition.action] = current_q + self.config.learning_rate * td_error
        return td_error

    def replay(self, buffer: ReplayBuffer, batch_size: int = 32) -> float:
        batch = buffer.sample(batch_size)
        if not batch:
            return 0.0
        errors = [abs(self.update(t)) for t in batch]
        return sum(errors) / len(errors)

    def decay_exploration(self) -> None:
        self.config.exploration_rate = max(
            self.config.min_exploration_rate,
            self.config.exploration_rate * self.config.exploration_decay,
        )

    def export_policy(self, candidate_actions: Dict[State, List[Action]]) -> Dict[State, Action]:
        policy: Dict[State, Action] = {}
        for state, actions in candidate_actions.items():
            if actions:
                policy[state] = self.greedy_action(state, actions)
        return policy

    def save(self, file_path: str | Path) -> None:
        """Write the model as JSON atomically (temp file + rename), so readers never see a partial file."""
        payload = {
            "schema_version": 2,
            "config": asdict(self.config),
            "q_table": self.q_table,
            "episode_rewards": self.episode_rewards,
        }
        _write_json_atomic(Path(file_path), payload)

    @classmethod
    def load(cls, file_path: str | Path) -> "QLearningAgent":
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        cfg = payload.get("config", {})
        agent = cls(config=RLConfig(**cfg))
        agent.q_table = payload.get("q_table", {})
        agent.episode_rewards = payload.get("episode_rewards", [])
        return agent

    def _ensure_state_actions(self, state: State, actions: Iterable[Action]) -> None:
        if state not in self.q_table:
            self.q_table[state] = {}
        for action in actions:
            self.q_table[state].setdefault(action, self.config.optimistic_initial_q)


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def migrate_model_document(payload: dict) -> dict:
    """Return a schema-version-3 model document, converting version 2 if needed.

    Version 2 held one agent shared by both problems. Its inference_* states move to
    problem_b; every other state, the shared config and episode_rewards move to
    problem_a (they came from retrieval training and ollama-mcp turns). problem_b gets
    the inference config (discount_factor 0.0) and an empty episode_rewards list.
    """
    version = payload.get("schema_version")
    if version == MODEL_SCHEMA_VERSION:
        return payload
    if "q_table" not in payload:
        raise ValueError(f"unrecognised model file (schema_version={version!r})")
    q_table = payload.get("q_table", {})
    return {
        "schema_version": MODEL_SCHEMA_VERSION,
        PROBLEM_A: {
            "config": payload.get("config") or asdict(retrieval_config()),
            "q_table": {s: a for s, a in q_table.items() if not s.startswith("inference_")},
            "episode_rewards": payload.get("episode_rewards", []),
        },
        PROBLEM_B: {
            "config": asdict(inference_config()),
            "q_table": {s: a for s, a in q_table.items() if s.startswith("inference_")},
            "episode_rewards": [],
        },
    }


def _read_model_document(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": MODEL_SCHEMA_VERSION}
    return migrate_model_document(json.loads(path.read_text(encoding="utf-8")))


def _agent_from_section(section: dict | None, problem: str) -> QLearningAgent:
    if not section:
        return QLearningAgent(config=default_config(problem))
    agent = QLearningAgent(config=RLConfig(**(section.get("config") or asdict(default_config(problem)))))
    if problem == PROBLEM_B:
        agent.config.discount_factor = 0.0  # Problem B is always single-step
    agent.q_table = section.get("q_table", {})
    agent.episode_rewards = section.get("episode_rewards", [])
    return agent


def _section_from_agent(agent: QLearningAgent) -> dict:
    return {
        "config": asdict(agent.config),
        "q_table": agent.q_table,
        "episode_rewards": agent.episode_rewards,
    }


def load_problem(file_path: str | Path, problem: str) -> QLearningAgent:
    """Load one problem's agent from the model file (version 2 files are migrated in memory only)."""
    default_config(problem)  # validates the name
    return _agent_from_section(_read_model_document(Path(file_path)).get(problem), problem)


def locked_update(
    file_path: str | Path,
    apply: Callable[[QLearningAgent], None],
    problem: str,
) -> QLearningAgent:
    """Apply a change to one problem's saved agent without discarding other updates.

    sr8-mcp, ollama-mcp and scripts/review-links.py each keep their own in-memory agent
    loaded from the same JSON file. Saving an in-memory copy would overwrite everything
    the others saved since it was loaded. Instead this takes an exclusive lock on
    <file>.lock, reloads the latest file (migrating version 2), applies the change to
    the given problem's agent only, writes the file atomically with the other problem's
    section untouched, and returns the updated agent; callers should use that as their
    new in-memory copy.
    """
    default_config(problem)  # validates the name
    path = Path(file_path)
    with open(f"{path}.lock", "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            document = _read_model_document(path)
            agent = _agent_from_section(document.get(problem), problem)
            apply(agent)
            document[problem] = _section_from_agent(agent)
            document["schema_version"] = MODEL_SCHEMA_VERSION
            _write_json_atomic(path, document)
            return agent
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def migrate_model_file(file_path: str | Path) -> bool:
    """Rewrite a version-2 model file as version 3 under the lock. Returns True if it changed."""
    path = Path(file_path)
    with open(f"{path}.lock", "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("schema_version") == MODEL_SCHEMA_VERSION:
                return False
            _write_json_atomic(path, migrate_model_document(raw))
            return True
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


# Problem A (retrieval strategy) deliberately has NO synthetic prior. The earlier toy
# environment trained a state ("adr_question") that ollama-mcp never produces and made up
# rewards for graph_first / documents_first / hybrid; its Q-values could not transfer to the
# live states (adr_lookup, general_lookup) and its training also decayed Problem A's epsilon.
# Problem A therefore learns only from live ollama-mcp turns. Its saved adr_lookup
# Q-values were reset to 0.0 (they had been learned under an earlier reward that counted
# client-appended evidence as a citation), its epsilon to the default 0.15, and its
# episode_rewards (all from the toy environment) cleared.


# Designer-specified cold-start prior for Problem B, NOT learned from data: hand-chosen
# Gaussian reward (mean, std) per evidence category and action, used only by
# train_inference_agent to give the live agent sensible starting Q-values before any
# human feedback exists. Real feedback from reviewers then updates the Q-table.
INFERENCE_PRIOR_REWARD_MODEL: Dict[str, Dict[Action, Tuple[float, float]]] = {
    "strong": {
        "increase_confidence": (0.8, 0.12),
        "keep_confidence":     (0.6, 0.12),
        "decrease_confidence": (-0.2, 0.08),
    },
    "moderate": {
        "increase_confidence": (0.1, 0.10),
        "keep_confidence":     (0.5, 0.12),
        "decrease_confidence": (-0.1, 0.08),
    },
    "weak": {
        "increase_confidence": (-0.5, 0.12),
        "keep_confidence":     (0.3, 0.12),
        "decrease_confidence": (0.6, 0.12),
    },
}


def inference_prior_category(state: State) -> str:
    """Map an inference state to its INFERENCE_PRIOR_REWARD_MODEL category.

    strong: inference_strong_* (>= 3 same-ADR requirements already assigned)
    moderate: inference_weak_yes_* (project already holds a same-ADR requirement) or
              inference_weak_no_mid
    weak: inference_weak_no_high, inference_weak_no_low
    """
    if state.startswith("inference_strong_"):
        return "strong"
    if "weak_yes" in state or state.endswith("_no_mid"):
        return "moderate"
    return "weak"


def train_inference_agent(
    episodes: int = 1000,
    replay_batch_size: int = 16,
    replay_every: int = 5,
    seed: int = 99,
) -> QLearningAgent:
    """Pre-train the Problem B agent on the 12 inference confidence-adjustment states.

    Produces a cold-start prior so the live system does not begin from uniform
    randomness. Single-step: each episode is one (state, action, reward) decision and
    the update is Q <- Q + alpha * (r - Q), using inference_config() (discount_factor
    0.0). States are sampled uniformly from INFERENCE_STATES; rewards are drawn from
    INFERENCE_PRIOR_REWARD_MODEL (designer-specified, not data) and clipped to [-1, 1].
    """
    random.seed(seed)
    agent = QLearningAgent(config=inference_config())
    buffer = ReplayBuffer(capacity=2000)

    for episode in range(1, episodes + 1):
        state = random.choice(INFERENCE_STATES)
        action = agent.choose_action(state, INFERENCE_ACTIONS)
        mean, noise = INFERENCE_PRIOR_REWARD_MODEL[inference_prior_category(state)][action]
        reward = max(-1.0, min(1.0, random.gauss(mean, noise)))

        transition = Transition(state, action, reward, state, [])  # no next state: one-step
        buffer.push(transition)
        agent.update(transition)

        if episode % replay_every == 0:
            agent.replay(buffer, replay_batch_size)

        agent.episode_rewards.append(reward)
        agent.decay_exploration()

    return agent


def format_q_table(agent: QLearningAgent, states: List[State], actions: List[Action]) -> str:
    """Return a plain-text table of Q-values and the greedy action for each state."""
    header = f"{'State':<28}" + "".join(f"{a:>22}" for a in actions) + f"  {'Greedy action':<22}"
    lines = [header, "-" * len(header)]
    for state in states:
        q = agent.q_table.get(state, {})
        greedy = max(actions, key=lambda a: q.get(a, float("-inf"))) if q else "-"
        lines.append(f"{state:<28}" + "".join(f"{q.get(a, 0.0):>22.4f}" for a in actions) + f"  {greedy:<22}")
    return "\n".join(lines)


def run_self_test() -> None:
    """Run a deterministic smoke/regression test of the learner (no model file is touched).

    Uses a three-armed toy bandit with neutral names that match no real state, so nothing
    it learns could be mistaken for a prior. Also checks the Problem B cold-start prior.
    """
    import tempfile

    random.seed(123)
    arms = ["arm_low", "arm_mid", "arm_high"]
    means = {"arm_low": 0.2, "arm_mid": 0.35, "arm_high": 0.75}
    agent = QLearningAgent(config=RLConfig(discount_factor=0.0))
    for _ in range(700):
        arm = agent.choose_action("self_test", arms)
        reward = max(-1.0, min(1.0, random.gauss(means[arm], 0.3)))
        agent.update(Transition("self_test", arm, reward, "self_test", []))
        agent.decay_exploration()
    greedy = agent.greedy_action("self_test", arms)
    assert greedy == "arm_high", f"unexpected greedy action: {greedy}"

    # Save/load round trip in a temporary directory.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "self-test.json"
        agent.save(tmp_path)
        assert QLearningAgent.load(tmp_path).q_table == agent.q_table, "q_table mismatch after save/load"

    prior = train_inference_agent()
    assert prior.config.discount_factor == 0.0, "Problem B prior must be single-step"
    assert set(prior.q_table) == set(INFERENCE_STATES), "Problem B prior must cover all 12 states"

    print("SELF-TEST PASSED")
    print(f"greedy_action={greedy} q={agent.q_table['self_test'][greedy]:.3f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extended Q-learning helper for thesis-extension")
    parser.add_argument("--self-test", action="store_true", help="Run built-in tests")
    parser.add_argument("--inference-table", action="store_true",
                        help="Train the Problem B cold-start prior (seed 99, 1000 episodes) and print its Q-table")
    parser.add_argument("--migrate", type=str, default="", metavar="PATH",
                        help="Rewrite a version-2 model file as version 3 (problem_a / problem_b)")
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
    elif args.inference_table:
        prior = train_inference_agent()
        print(f"Problem B cold-start prior: train_inference_agent(episodes=1000, seed=99), "
              f"discount_factor={prior.config.discount_factor}, final epsilon={prior.config.exploration_rate:.4f}")
        print(format_q_table(prior, INFERENCE_STATES, INFERENCE_ACTIONS))
    elif args.migrate:
        changed = migrate_model_file(args.migrate)
        print(f"{args.migrate}: {'migrated to schema version 3' if changed else 'already schema version 3'}")
    else:
        parser.print_help()
