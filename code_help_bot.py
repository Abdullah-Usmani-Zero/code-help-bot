"""Code help bot: count a source file's tokens with tiktoken, then ask Claude about it.

Usage:
    python code_help_bot.py --count-only                 # just print token counts for client.py
    python code_help_bot.py "How does retry work here?"  # count tokens, then ask Claude
    python code_help_bot.py -f other.py "Explain this file"

Pipeline stages (see README "Pipeline stages"):
    1. Load source      2. Tokenize (tiktoken)      3. Budget check (tiktoken, then Claude tokenizer)
    4. Ask Claude       5. Report usage             6. Audit answers (not automated yet)
Retrieval stages R1-R6 are placeholders: until they exist the bot can only send the whole file,
which is over the input budget, so every question is refused at stage 3.
"""

import argparse
import sys
from pathlib import Path

import tiktoken

DEFAULT_FILE = Path(__file__).with_name("client.py")
ENCODINGS = ("cl100k_base", "o200k_base")
BUDGET_ENCODING = "cl100k_base"  # same encoding as the pilot audit's token column
MODEL = "claude-opus-5"

# Hard per-question budget. See README "Per-question token budget".
BASELINE_TOKENS = 3_940  # whole client.py in cl100k_base: what the whole-file bot sends before any question
MAX_BUDGET_SHARE = 0.30  # the budget must stay under 30% of the baseline
INPUT_BUDGET = 750  # system prompt + retrieved context + question
OUTPUT_BUDGET = 400  # thinking + answer, enforced by the API through max_tokens
PER_QUESTION_BUDGET = INPUT_BUDGET + OUTPUT_BUDGET  # 1,150 = 29.2% of baseline
assert PER_QUESTION_BUDGET < MAX_BUDGET_SHARE * BASELINE_TOKENS, "budget must be under 30% of baseline"

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


def pct(n: int) -> str:
    return f"{n / BASELINE_TOKENS:.1%} of baseline"


def check_input_offline(user_message: str) -> int:
    """Stage 3a: count the prompt with tiktoken before any API call; refuse if over budget."""
    n = len(tiktoken.get_encoding(BUDGET_ENCODING).encode(SYSTEM_PROMPT + user_message))
    print(f"  input tokens ({BUDGET_ENCODING}): {n} / {INPUT_BUDGET} budget ({pct(n)})")
    if n > INPUT_BUDGET:
        raise BudgetExceeded(f"prompt is {n} tokens, over the {INPUT_BUDGET}-token input budget")
    return n


def ask_claude(user_message: str):
    import anthropic

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user_message}]

    # Stage 3b: recount with Claude's own tokenizer before any tokens are spent.
    input_tokens = client.messages.count_tokens(
        model=MODEL, system=SYSTEM_PROMPT, thinking={"type": "adaptive"}, messages=messages
    ).input_tokens
    print(f"  Claude input tokens (count_tokens): {input_tokens} / {INPUT_BUDGET} budget")
    if input_tokens > INPUT_BUDGET:
        raise BudgetExceeded(f"input is {input_tokens} tokens, over the {INPUT_BUDGET}-token input budget")

    # Stage 4: ask Claude. max_tokens caps thinking + answer at the output budget;
    # low effort keeps thinking short so the answer fits inside it.
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=OUTPUT_BUDGET,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "low"},
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
    print(f"  baseline: {BASELINE_TOKENS} tokens (whole client.py, {BUDGET_ENCODING})")
    print(f"  per-question budget: {PER_QUESTION_BUDGET} tokens = {INPUT_BUDGET} input + {OUTPUT_BUDGET} output "
          f"({pct(PER_QUESTION_BUDGET)}; cap is {MAX_BUDGET_SHARE:.0%})")

    if args.count_only:
        return 0
    if not args.question:
        parser.error("a question is required unless --count-only is set")

    # [PLACEHOLDER] Retrieval stages R1-R6 go here and replace `source` with the chunks relevant
    # to the question. Until then the context is the whole file (the baseline being improved on).
    user_message = build_user_message(source, args.file.name, args.question)

    import anthropic

    try:
        check_input_offline(user_message)
        response = ask_claude(user_message)
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
    total = usage.input_tokens + usage.output_tokens
    print(f"  actual usage: {usage.input_tokens} input + {usage.output_tokens} output = "
          f"{total} / {PER_QUESTION_BUDGET} budget ({pct(total)}; "
          f"stop_reason: {response.stop_reason}, model: {response.model})")
    if response.stop_reason == "max_tokens":
        print("  warning: answer was cut off at the output budget", file=sys.stderr)

    print()
    print("".join(block.text for block in response.content if block.type == "text"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
