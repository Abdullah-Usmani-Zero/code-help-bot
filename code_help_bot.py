"""Code help bot: count a source file's tokens with tiktoken, then ask Claude about it.

Usage:
    python code_help_bot.py --count-only                 # just print token counts for client.py
    python code_help_bot.py "How does retry work here?"  # count tokens, then ask Claude
    python code_help_bot.py -f other.py "Explain this file"

Pipeline stages (see README "Pipeline stages"):
    1. Load source      2. Tokenize (tiktoken)      3. Budget check (Claude tokenizer)
    4. Ask Claude       5. Report usage             6. Audit answers (not automated yet)
"""

import argparse
import sys
from pathlib import Path

import tiktoken

DEFAULT_FILE = Path(__file__).with_name("client.py")
ENCODINGS = ("cl100k_base", "o200k_base")
MODEL = "claude-opus-5"

# Hard per-question budget, in Claude tokens. See README "Per-question token budget".
INPUT_BUDGET = 6_500  # system prompt + wrapped file + question, checked with count_tokens before sending
OUTPUT_BUDGET = 8_000  # thinking + answer, enforced by the API through max_tokens
PER_QUESTION_BUDGET = INPUT_BUDGET + OUTPUT_BUDGET  # 14,500

SYSTEM_PROMPT = (
    "You are a code help assistant. The user will share a Python source file and a "
    "question about it. Answer using the code as your source of truth, cite the "
    "relevant function or class names, and include short code snippets when they help."
)


class BudgetExceeded(Exception):
    pass


def count_tokens(text: str) -> dict[str, int]:
    """Return the exact token count of `text` for each tiktoken encoding."""
    return {name: len(tiktoken.get_encoding(name).encode(text)) for name in ENCODINGS}


def build_user_message(source: str, filename: str, question: str) -> str:
    return f"<file name=\"{filename}\">\n{source}\n</file>\n\n{question}"


def ask_claude(source: str, filename: str, question: str):
    import anthropic

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": build_user_message(source, filename, question)}]

    # Stage 3: budget check, counted with Claude's own tokenizer before any tokens are spent.
    input_tokens = client.messages.count_tokens(
        model=MODEL, system=SYSTEM_PROMPT, thinking={"type": "adaptive"}, messages=messages
    ).input_tokens
    print(f"  Claude input tokens (count_tokens): {input_tokens} / {INPUT_BUDGET} budget")
    if input_tokens > INPUT_BUDGET:
        raise BudgetExceeded(f"input is {input_tokens} tokens, over the {INPUT_BUDGET}-token input budget")

    # Stage 4: ask Claude. max_tokens caps thinking + answer at the output budget.
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=OUTPUT_BUDGET,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        # On a policy decline, the API re-runs the request on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=messages,
    )
    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        raise RuntimeError(f"Claude declined the request (category: {category})")
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", nargs="?", help="question to ask Claude about the file")
    parser.add_argument("-f", "--file", type=Path, default=DEFAULT_FILE, help="source file (default: client.py)")
    parser.add_argument("--count-only", action="store_true", help="print token counts and exit")
    args = parser.parse_args()

    # Stage 1: load source.
    source = args.file.read_text(encoding="utf-8")
    print(f"{args.file.name}: {len(source)} characters, {len(source.splitlines())} lines")

    # Stage 2: tokenize with tiktoken (offline, no API key needed).
    for name, n in count_tokens(source).items():
        print(f"  tiktoken {name}: {n} tokens")
    fixed_prompt = SYSTEM_PROMPT + build_user_message(source, args.file.name, "")
    for name, n in count_tokens(fixed_prompt).items():
        print(f"  tiktoken {name}, system prompt + wrapped file: {n} tokens")
    print(f"  per-question budget: {PER_QUESTION_BUDGET} Claude tokens "
          f"({INPUT_BUDGET} input + {OUTPUT_BUDGET} output)")

    if args.count_only:
        return 0
    if not args.question:
        parser.error("a question is required unless --count-only is set")

    import anthropic

    try:
        response = ask_claude(source, args.file.name, args.question)
    except BudgetExceeded as e:
        print(f"Over budget, not sent: {e}.", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    except anthropic.AuthenticationError:
        print("Authentication failed: set ANTHROPIC_API_KEY.", file=sys.stderr)
        return 1
    except anthropic.RateLimitError:
        print("Rate limited by the Claude API; try again shortly.", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as e:
        print(f"Claude API error {e.status_code}: {e.message}", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError:
        print("Could not reach the Claude API.", file=sys.stderr)
        return 1

    # Stage 5: report actual usage against the budget.
    usage = response.usage
    print(f"  actual usage: {usage.input_tokens} input + {usage.output_tokens} output = "
          f"{usage.input_tokens + usage.output_tokens} / {PER_QUESTION_BUDGET} budget "
          f"(stop_reason: {response.stop_reason}, model: {response.model})")
    if response.stop_reason == "max_tokens":
        print("  warning: answer was cut off at the output budget", file=sys.stderr)

    print()
    print("".join(block.text for block in response.content if block.type == "text"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
