"""Code help bot: count a source file's tokens with tiktoken, then ask Claude about it.

Usage:
    python code_help_bot.py --count-only                 # just print token counts for client.py
    python code_help_bot.py "How does retry work here?"  # count tokens, then ask Claude
    python code_help_bot.py -f other.py "Explain this file"
"""

import argparse
import sys
from pathlib import Path

import tiktoken

DEFAULT_FILE = Path(__file__).with_name("client.py")
ENCODINGS = ("cl100k_base", "o200k_base")
MODEL = "claude-opus-5"

SYSTEM_PROMPT = (
    "You are a code help assistant. The user will share a Python source file and a "
    "question about it. Answer using the code as your source of truth, cite the "
    "relevant function or class names, and include short code snippets when they help."
)


def count_tokens(text: str) -> dict[str, int]:
    """Return the exact token count of `text` for each tiktoken encoding."""
    return {name: len(tiktoken.get_encoding(name).encode(text)) for name in ENCODINGS}


def ask_claude(source: str, filename: str, question: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        # On a policy decline, the API re-runs the request on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[
            {
                "role": "user",
                "content": f"<file name=\"{filename}\">\n{source}\n</file>\n\n{question}",
            }
        ],
    )
    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        raise RuntimeError(f"Claude declined the request (category: {category})")
    return "".join(block.text for block in response.content if block.type == "text")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", nargs="?", help="question to ask Claude about the file")
    parser.add_argument("-f", "--file", type=Path, default=DEFAULT_FILE, help="source file (default: client.py)")
    parser.add_argument("--count-only", action="store_true", help="print token counts and exit")
    args = parser.parse_args()

    source = args.file.read_text(encoding="utf-8")
    print(f"{args.file.name}: {len(source)} characters, {len(source.splitlines())} lines")
    for name, n in count_tokens(source).items():
        print(f"  tiktoken {name}: {n} tokens")

    if args.count_only:
        return 0
    if not args.question:
        parser.error("a question is required unless --count-only is set")

    import anthropic

    try:
        answer = ask_claude(source, args.file.name, args.question)
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

    print()
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
