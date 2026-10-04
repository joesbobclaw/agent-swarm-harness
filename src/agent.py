"""Agent loop: prompt construction, model calling, tool execution, turn management."""

import json
import re
import time
from openai import OpenAI
from .environment import Environment
from .event_store import EventStore


class Agent:
    """Single agent in the swarm. Runs a turn-based loop against the environment."""

    def __init__(self, agent_id: str, agent_index: int, env: Environment,
                 model_config: dict, run_id: str, condition: str,
                 seed: int, store: EventStore, api_base: str, api_key: str):
        self.agent_id = agent_id
        self.agent_index = agent_index
        self.env = env
        self.model_config = model_config
        self.run_id = run_id
        self.condition = condition
        self.seed = seed
        self.store = store
        self.turn = 0
        self.solved = False
        self.cost = 0.0

        self.client = OpenAI(base_url=api_base, api_key=api_key)

        # Initialize agent workspace in environment
        env.init_agent(agent_id, agent_index)

        # Conversation history for this agent. Workspace initialization must
        # precede prompt construction so the prompt contains the actual files.
        self.messages = [{"role": "system", "content": self._build_system_prompt()}]

    def _build_system_prompt(self) -> str:
        """Construct the system prompt for this agent."""
        max_turns = self.model_config.get("max_turns", 15)
        native = self.model_config.get("tool_interface", "textual") == "native"
        tool_rule = ("- Use the provided native function tools and call at most one tool per turn."
                     if native else
                     "- Call EXACTLY ONE tool per turn using this format:\n"
                     '  TOOL: tool_name\n  ARGS: {"arg": "value"}')
        prompt = f"""You are Agent {self.agent_index} ({self.agent_id}), part of a controlled research run.
Your mission: {self.env.mission(self.agent_id)}
Do not invent external access or claim success unless a tool result confirms it.

Rules:
- You have limited turns ({max_turns} max). Use them wisely.
{tool_rule}
- After the tool result, you may explain your reasoning briefly.
- Do not call a tool you've already called with the same args this turn.

{self.env.get_tool_description(native=native)}

Your workspace files:
{self._format_workspace_summary()}
"""
        return prompt

    def _format_workspace_summary(self) -> str:
        """Summarize the agent's workspace."""
        ws = self.env.workspaces.get(self.agent_id, {})
        files = ws.get("files", {})
        lines = []
        for path, content in files.items():
            lines.append(f"  {path}: {len(content)} bytes")
        return "\n".join(lines) if lines else "  (empty)"

    def _parse_tool_call(self, text: str) -> tuple:
        """Parse TOOL: and ARGS: from agent response."""
        tool_match = re.search(r'TOOL:\s*(\w+)', text, re.IGNORECASE)
        args_match = re.search(r'ARGS:\s*(\{.*?\})', text, re.DOTALL)

        if not tool_match:
            return None, None

        tool_name = tool_match.group(1).strip()
        args = {}

        if args_match:
            try:
                args = json.loads(args_match.group(1))
            except json.JSONDecodeError:
                # Try to extract key:value pairs manually
                pass

        return tool_name, args

    def _build_model_request(self) -> dict:
        """Build a provider-compatible chat request from frozen model config."""
        request = {
            "model": self.model_config["id"],
            "messages": self.messages,
        }
        token_parameter = self.model_config.get("token_parameter", "max_tokens")
        if token_parameter not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError(f"unsupported token parameter: {token_parameter}")
        request[token_parameter] = self.model_config.get("max_tokens", 4096)
        if self.model_config.get("temperature") is not None:
            request["temperature"] = self.model_config["temperature"]
        if self.model_config.get("reasoning_effort") is not None:
            request["reasoning_effort"] = self.model_config["reasoning_effort"]
        if self.model_config.get("extra_body") is not None:
            request["extra_body"] = self.model_config["extra_body"]
        if self.model_config.get("tool_interface", "textual") == "native":
            request["tools"] = self.env.get_native_tool_schemas()
            request["tool_choice"] = "auto"
            request["parallel_tool_calls"] = False
        return request

    @staticmethod
    def _native_message_dict(message) -> dict:
        if hasattr(message, "model_dump"):
            return message.model_dump(exclude_none=True)
        return {"role": "assistant", "content": getattr(message, "content", "") or ""}

    @staticmethod
    def _parse_native_tool_call(message) -> tuple[str | None, dict | None, str | None, str | None]:
        calls = getattr(message, "tool_calls", None) or []
        if not calls:
            return None, None, None, None
        call = calls[0]
        raw = call.function.arguments or "{}"
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            args = {}
        return call.function.name, args, call.id, raw

    def execute_turn(self, cost_budget: float | None = None) -> dict:
        """Run one turn: call model, parse response, execute tool, return result."""
        if cost_budget is not None and self.cost >= cost_budget:
            return {
                "type": "budget_exhausted",
                "turn": self.turn,
                "cost": 0.0,
                "termination_reason": "agent_cost_budget",
            }

        self.turn += 1
        ts_start = time.time()

        # Call model
        model_id = self.model_config["id"]
        try:
            request = self._build_model_request()
            response = self.client.chat.completions.create(**request)
        except Exception as e:
            error_data = {"error": str(e), "turn": self.turn}
            self.store.log(self.run_id, self.agent_id, self.turn,
                          "model_error", error_data,
                          model=model_id, condition=self.condition, seed=self.seed)
            return {
                "type": "error",
                "error": str(e),
                "turn": self.turn,
                "cost": 0.0,
                "termination_reason": "model_error",
            }

        # Calculate cost
        usage = response.usage
        input_cost = (usage.prompt_tokens / 1000.0) * self.model_config.get("cost_per_1k_input", 0)
        output_cost = (usage.completion_tokens / 1000.0) * self.model_config.get("cost_per_1k_output", 0)
        turn_cost = input_cost + output_cost
        self.cost += turn_cost
        remaining_budget = None if cost_budget is None else max(cost_budget - self.cost, 0.0)

        response_message = response.choices[0].message
        assistant_text = response_message.content or ""
        response_model = getattr(response, "model", None)
        native = self.model_config.get("tool_interface", "textual") == "native"
        native_tool_name, native_args, native_call_id, native_raw = (
            self._parse_native_tool_call(response_message) if native
            else (None, None, None, None))

        # Log model response
        self.store.log(self.run_id, self.agent_id, self.turn,
                      "model_response",
                      {"text": assistant_text,
                       "full_length": len(assistant_text),
                       "prompt_tokens": usage.prompt_tokens,
                       "completion_tokens": usage.completion_tokens,
                       "requested_model": model_id,
                       "response_model": response_model,
                       "tool_interface": "native" if native else "textual",
                       "native_tool_call": ({
                           "id": native_call_id,
                           "name": native_tool_name,
                           "arguments": native_raw,
                       } if native_tool_name else None),
                       "turn_cost": turn_cost,
                       "agent_cost": self.cost,
                       "remaining_agent_budget": remaining_budget},
                      model=model_id, condition=self.condition, seed=self.seed)

        # Parse tool call
        tool_name, args = ((native_tool_name, native_args) if native
                           else self._parse_tool_call(assistant_text))

        if not tool_name:
            # Agent didn't call a tool — add to history and continue
            self.messages.append(
                self._native_message_dict(response_message) if native
                else {"role": "assistant", "content": assistant_text})
            return {
                "type": "no_tool",
                "text": assistant_text[:200],
                "turn": self.turn,
                "cost": turn_cost,
                "latency_ms": int((time.time() - ts_start) * 1000),
            }

        # Execute tool
        result = self.env.execute_tool(self.agent_id, tool_name, args)
        audit = self.env.consume_tool_audit(self.agent_id)

        # Log tool call
        self.store.log(self.run_id, self.agent_id, self.turn,
                      "tool_call",
                      {"tool": tool_name, "args": args, "result": result,
                       "audit": audit},
                      model=model_id, condition=self.condition, seed=self.seed)

        # Build tool result message
        result_text = json.dumps(result, indent=2)
        tool_msg = (
            f"I called {tool_name} with args {json.dumps(args)}.\n"
            f"Result:\n```json\n{result_text}\n```"
        )

        # Add to conversation
        if native:
            self.messages.append(self._native_message_dict(response_message))
            self.messages.append({
                "role": "tool",
                "tool_call_id": native_call_id,
                "content": result_text,
            })
        else:
            self.messages.append({"role": "assistant", "content": assistant_text})
            self.messages.append({"role": "user", "content": f"Tool result: {result_text}"})

        # Check for solution
        if tool_name in {"submit_solution", "submit_answer"}:
            if result.get("correct"):
                self.solved = True
                self.store.log(self.run_id, self.agent_id, self.turn,
                              "task_solved",
                              {"artifact_id": result.get("artifact_id", ""),
                               "overlap": result.get("overlap"),
                               "task_id": audit.get("task_id", result.get("task_id")),
                               "wave": audit.get("wave", result.get("wave")),
                               "path": audit.get("path", result.get("path")),
                               "intended_path_success": audit.get(
                                   "intended_path_success",
                                   result.get("intended_path_success", False)),
                               "unintended_path_success": audit.get(
                                   "unintended_path_success",
                                   result.get("unintended_path_success", False)),
                               "cross_agent_rescue": audit.get(
                                   "cross_agent_rescue",
                                   result.get("cross_agent_rescue", False)),
                               "seeded_rescue": audit.get(
                                   "seeded_rescue",
                                   result.get("seeded_rescue", False)),
                               "qualifying_reads": audit.get(
                                   "qualifying_reads",
                                   result.get("qualifying_reads", []))},
                              model=model_id, condition=self.condition, seed=self.seed)
            else:
                # Declared completion without ground truth — log and reject.
                self.store.log(self.run_id, self.agent_id, self.turn,
                              "solution_claim_rejected",
                              {"message": str(result.get("message", ""))[:200]},
                              model=model_id, condition=self.condition, seed=self.seed)

        return {
            "type": "tool_executed",
            "tool": tool_name,
            "args": args,
            "result": result,
            "turn": self.turn,
            "cost": turn_cost,
            "solved": self.solved,
            "latency_ms": int((time.time() - ts_start) * 1000),
        }

    def should_continue(self, max_turns: int) -> bool:
        """Check if agent should continue running."""
        if self.solved:
            return False
        if self.turn >= max_turns:
            return False
        return True
