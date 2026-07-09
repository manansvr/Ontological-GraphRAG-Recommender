"""Extended reinforcement learning helper for thesis-extension.

This file keeps the exact user-requested name: reinforcemnt-learning.py.

It provides a more complete tabular Q-learning toolkit with:
- epsilon-greedy exploration
- optional experience replay
- training/evaluation helpers
- policy export
- JSON persistence
- built-in self-tests
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, asdict
import json
import random
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Tuple


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
        payload = {
            "schema_version": 2,
            "config": asdict(self.config),
            "q_table": self.q_table,
            "episode_rewards": self.episode_rewards,
        }
        Path(file_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

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


class RetrievalBanditEnvironment:
    """Toy environment to simulate retrieval strategy feedback.

    The "hybrid" strategy is best for ADR questions in this synthetic setup.
    """

    def __init__(self) -> None:
        self.state = "adr_question"
        self.actions = ["graph_first", "documents_first", "hybrid"]
        self.reward_model = {
            "graph_first": (0.2, 0.35),
            "documents_first": (0.35, 0.35),
            "hybrid": (0.75, 0.25),
        }

    def reset(self) -> Tuple[State, List[Action]]:
        return self.state, self.actions[:]

    def step(self, action: Action) -> Tuple[float, State, List[Action]]:
        mean, noise = self.reward_model[action]
        reward = random.gauss(mean, noise)
        reward = max(-1.0, min(1.0, reward))
        next_state = self.state
        next_actions = self.actions[:]
        return reward, next_state, next_actions


def train_agent(
    episodes: int = 600,
    replay_batch_size: int = 16,
    replay_every: int = 5,
    seed: int = 42,
) -> QLearningAgent:
    random.seed(seed)
    env = RetrievalBanditEnvironment()
    agent = QLearningAgent()
    buffer = ReplayBuffer(capacity=2000)

    for episode in range(1, episodes + 1):
        state, actions = env.reset()
        action = agent.choose_action(state, actions)
        reward, next_state, next_actions = env.step(action)

        transition = Transition(state, action, reward, next_state, next_actions)
        buffer.push(transition)
        agent.update(transition)

        if episode % replay_every == 0:
            agent.replay(buffer, replay_batch_size)

        agent.episode_rewards.append(reward)
        agent.decay_exploration()

    return agent


def train_inference_agent(
    episodes: int = 1000,
    replay_batch_size: int = 16,
    replay_every: int = 5,
    seed: int = 99,
) -> QLearningAgent:
    """Pre-train a Q-learning agent on the 12 inference confidence-adjustment states.

    Produces a sensible prior so the live system does not begin from uniform randomness.
    The 12 states are: inference_{strong|weak}_{yes|no}_{high|mid|low}.

    Reward model:
    - Strong evidence (inference_strong_*):         increase=0.8, keep=0.6, decrease=-0.2
    - Moderate evidence (inference_weak_yes_* or
      inference_*_no_mid):                          increase=0.1, keep=0.5, decrease=-0.1
    - Weak evidence (inference_weak_no_{high|low}): increase=-0.5, keep=0.3, decrease=0.6
    """
    random.seed(seed)

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

    # Reward means and noise std for each (category, action) pair.
    REWARD_MODELS: Dict[str, Dict[str, Tuple[float, float]]] = {
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

    def _category(state: State) -> str:
        if state.startswith("inference_strong_"):
            return "strong"
        # Moderate: weak+yes or any state ending in _no_mid (but not already strong).
        if "weak_yes" in state or state.endswith("_no_mid"):
            return "moderate"
        return "weak"

    agent = QLearningAgent()
    buffer = ReplayBuffer(capacity=2000)

    for episode in range(1, episodes + 1):
        state = random.choice(INFERENCE_STATES)
        action = agent.choose_action(state, INFERENCE_ACTIONS)
        mean, noise = REWARD_MODELS[_category(state)][action]
        reward = max(-1.0, min(1.0, random.gauss(mean, noise)))

        transition = Transition(state, action, reward, state, INFERENCE_ACTIONS)
        buffer.push(transition)
        agent.update(transition)

        if episode % replay_every == 0:
            agent.replay(buffer, replay_batch_size)

        agent.episode_rewards.append(reward)
        agent.decay_exploration()

    return agent


def evaluate_policy(agent: QLearningAgent, episodes: int = 200, seed: int = 7) -> Dict[str, float]:
    random.seed(seed)
    env = RetrievalBanditEnvironment()
    state, actions = env.reset()

    greedy = agent.greedy_action(state, actions)
    rewards = []
    for _ in range(episodes):
        reward, _, _ = env.step(greedy)
        rewards.append(reward)

    avg_reward = sum(rewards) / len(rewards)
    return {
        "greedy_action": greedy,
        "avg_reward": avg_reward,
    }


def run_self_test() -> None:
    """Run a deterministic smoke/regression test for this module."""
    agent = train_agent(episodes=700, seed=123)
    report = evaluate_policy(agent, episodes=300, seed=456)

    # Verify learned strategy and Q ordering for this toy setup.
    state = "adr_question"
    actions = ["graph_first", "documents_first", "hybrid"]
    q_values = {a: agent.q_value(state, a) for a in actions}

    assert report["greedy_action"] == "hybrid", f"unexpected greedy action: {report['greedy_action']}"
    assert q_values["hybrid"] >= q_values["documents_first"], "hybrid should outrank documents_first"
    assert q_values["hybrid"] >= q_values["graph_first"], "hybrid should outrank graph_first"
    assert report["avg_reward"] > 0.45, f"average reward too low: {report['avg_reward']:.3f}"

    # Verify save/load round trip.
    tmp_path = Path(".rl-self-test.json")
    agent.save(tmp_path)
    reloaded = QLearningAgent.load(tmp_path)
    tmp_path.unlink(missing_ok=True)
    assert reloaded.q_table == agent.q_table, "q_table mismatch after save/load"

    print("SELF-TEST PASSED")
    print(f"greedy_action={report['greedy_action']} avg_reward={report['avg_reward']:.3f}")


def run_demo(save_path: str | None = None, episodes: int = 600) -> None:
    agent = train_agent(episodes=episodes)
    report = evaluate_policy(agent)

    print("Training complete")
    print(f"episodes={episodes}")
    print(f"final_exploration_rate={agent.config.exploration_rate:.4f}")
    print(f"greedy_action={report['greedy_action']}")
    print(f"avg_reward={report['avg_reward']:.3f}")

    if save_path:
        agent.save(save_path)
        print(f"saved_model={save_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extended Q-learning helper for thesis-extension")
    parser.add_argument("--self-test", action="store_true", help="Run built-in tests")
    parser.add_argument("--episodes", type=int, default=600, help="Training episodes for demo")
    parser.add_argument("--save", type=str, default="", help="Optional JSON path to save trained model")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.self_test:
        run_self_test()
    else:
        run_demo(save_path=args.save or None, episodes=args.episodes)
