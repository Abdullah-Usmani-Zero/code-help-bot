# code-help-bot

A small bot pipeline: take a source file, count its tokens with
[tiktoken](https://github.com/openai/tiktoken), check the request against a hard token budget,
then ask Claude a question about the file.

## Files

| File | What it is |
| --- | --- |
| `client.py` | Downloaded verbatim from [ramnes/notion-sdk-py](https://github.com/ramnes/notion-sdk-py) — `notion_client/client.py` at commit `a94e6dfe47f8a44cf642fa6bb7d6c4e6f8468108` (MIT license, © Guillaume Gelin — see `LICENSE-notion-sdk-py`). SHA-256 `95e5aa4fdfd8616d047124ac096e3be708223809f91804839a38483204e9eeb5`. |
| `code_help_bot.py` | Runs the pipeline below against `client.py` (or any file passed with `-f`). |
| `evidence/tiktoken_run.txt` | Verbatim terminal output of the tiktoken run the token counts come from. |

## Pipeline stages

| # | Stage | Where | Status |
| --- | --- | --- | --- |
| 1 | **Load source** — read the target file | `main()` | Done |
| 2 | **Tokenize** — exact tiktoken counts for the file and for the fixed prompt | `count_tokens()` | Done — output below |
| 3 | **Budget check** — count the real request with Claude's tokenizer (`messages.count_tokens`); refuse to send if over the input budget | `ask_claude()` | Done — tested with a mocked API; `[PENDING: first live count_tokens figure]` |
| 4 | **Ask Claude** — `claude-opus-5`, adaptive thinking, `max_tokens` = output budget | `ask_claude()` | Done — `[PENDING: first live answer; needs ANTHROPIC_API_KEY]` |
| 5 | **Report usage** — actual input/output tokens against the budget; warns if the answer was cut off | `main()` | Done — tested with a mocked API |
| 6 | **Audit answers** — grade pilot answers and record the figures below | `pilot_answer_audit.xlsx` | `[PLACEHOLDER: not automated; figures pending]` |

## Token count for `client.py`

| Measurement | `cl100k_base` (GPT-4 / GPT-3.5) | `o200k_base` (GPT-4o) |
| --- | --- | --- |
| `client.py` alone | **3,940** | **3,945** |
| System prompt + wrapped file (the fixed part of every request) | 3,997 | 4,002 |

These are OpenAI tokenizer counts. Claude uses its own tokenizer, which is why stage 3 recounts
every request with `messages.count_tokens` before sending it.

### Terminal output

Captured 2026-09-25 from the repo root (full session, including date and Python version, in
`evidence/tiktoken_run.txt`). The last command recounts with tiktoken directly, independent of
the bot's code:

```text
$ python3 -c "import tiktoken; print(\"tiktoken\", tiktoken.__version__)"
tiktoken 0.14.0

$ sha256sum client.py
95e5aa4fdfd8616d047124ac096e3be708223809f91804839a38483204e9eeb5  client.py

$ wc -c -l client.py
  513 18097 client.py

$ python3 code_help_bot.py --count-only
client.py: 18097 characters, 513 lines
  tiktoken cl100k_base: 3940 tokens
  tiktoken o200k_base: 3945 tokens
  tiktoken cl100k_base, system prompt + wrapped file: 3997 tokens
  tiktoken o200k_base, system prompt + wrapped file: 4002 tokens
  per-question budget: 14500 Claude tokens (6500 input + 8000 output)

$ python3 -c "import tiktoken; t=open(\"client.py\",encoding=\"utf-8\").read(); [print(e, len(tiktoken.get_encoding(e).encode(t))) for e in (\"cl100k_base\",\"o200k_base\")]"
cl100k_base 3940
o200k_base 3945
```

The sandbox this ran in could not reach OpenAI's download host, so tiktoken read its vocabulary
files from a local cache (`TIKTOKEN_CACHE_DIR`). tiktoken checks every vocabulary file against the
SHA-256 pinned in its source before using it (`cl100k_base` `223921b7…`, `o200k_base` `446a9538…`),
so the counts are the same as a normal install produces. Anyone can reproduce them with
`pip install tiktoken==0.14.0 && python code_help_bot.py --count-only`.

## Per-question token budget

**Hard budget: 14,500 Claude tokens per question** = 6,500 input + 8,000 output.
The numbers are constants at the top of `code_help_bot.py`.

| Part | Budget | How it's enforced | Why this number |
| --- | --- | --- | --- |
| Input (system prompt + file + question) | **6,500** | Stage 3 counts the exact request with `messages.count_tokens` and does not send it if the count is over 6,500. | The fixed prompt is 4,002 tokens (o200k). The budget allows about 50% extra, up to ~6,000, because Claude's tokenizer can count the same text higher than tiktoken, plus ~500 tokens for the question. |
| Output (thinking + answer) | **8,000** | Passed as `max_tokens`; the API stops generation at this limit. Stage 5 warns if an answer was cut off (`stop_reason: max_tokens`). | Enough for adaptive thinking plus an answer with code snippets about a ~4k-token file, while capping the cost of any single question. |
| **Total** | **14,500** | Stage 5 prints actual `usage` against this total after every answer. | Sum of the two. |

The 50% input headroom is an assumption until the first live run. Stage 3 prints the real
Claude count, which confirms or corrects it: `[PENDING: count_tokens figure for client.py + a sample question]`.

## Audit results — `pilot_answer_audit.xlsx`

`[PLACEHOLDER: figures to be filled from pilot_answer_audit.xlsx — none of the values below are measured yet]`

| Figure | Value |
| --- | --- |
| Questions audited | `[PENDING]` |
| Answers judged correct | `[PENDING]` |
| Accuracy | `[PENDING]` |
| Mean tokens per question (input + output) | `[PENDING]` |
| Max tokens on any question | `[PENDING]` |
| Questions over the 14,500-token budget | `[PENDING]` |
| Answers cut off at the output budget | `[PENDING]` |

## Usage

```bash
pip install -r requirements.txt
python code_help_bot.py --count-only
export ANTHROPIC_API_KEY=...
python code_help_bot.py "How does the retry logic in client.py work?"
python code_help_bot.py -f some_other_file.py "Explain this file"
```
