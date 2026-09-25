# code-help-bot

A small bot pipeline: take a source file, count its tokens with
[tiktoken](https://github.com/openai/tiktoken), check the request against a hard token budget,
then ask Claude a question about the file.

The pilot this replaces sent the **whole file** with every question. Its audit (below) found that
14 of 24 answers contained a fabricated detail, and that none of those 14 cited where in the file
the answer came from. The goal is to beat that bot on both cost and grounding: send only the parts
of the file a question needs, and require citations.

## Files

| File | What it is |
| --- | --- |
| `client.py` | Downloaded verbatim from [ramnes/notion-sdk-py](https://github.com/ramnes/notion-sdk-py) — `notion_client/client.py` at commit `a94e6dfe47f8a44cf642fa6bb7d6c4e6f8468108` (MIT license, © Guillaume Gelin — see `LICENSE-notion-sdk-py`). SHA-256 `95e5aa4fdfd8616d047124ac096e3be708223809f91804839a38483204e9eeb5`. |
| `code_help_bot.py` | Runs the pipeline below against `client.py` (or any file passed with `-f`). |
| `evidence/tiktoken_run.txt` | Verbatim terminal output of the tiktoken run the token counts come from. |
| `evidence/audit_figures.py` / `.txt` | Script that recomputes the audit figures from `pilot_answer_audit.xlsx`, and its output. The spreadsheet itself is not committed: it names individual engineers and this repo is public. |
| `evidence/pilot_upstream_check.txt` | Token counts of the files the pilot used, measured at the upstream commit in use when the pilot ran. |

## Pipeline stages

| # | Stage | Where | Status |
| --- | --- | --- | --- |
| 1 | **Load source** — read the target file | `main()` | Done |
| 2 | **Tokenize** — exact tiktoken counts for the file and for the fixed prompt | `count_tokens()` | Done — output below |
| R1–R6 | **Retrieval** — replace the whole file with the chunks the question needs (next table) | `main()`, marked `[PLACEHOLDER]` | `[PLACEHOLDER: not built]` |
| 3a | **Budget check, offline** — count the prompt with tiktoken; refuse before any API call if over the input budget | `check_input_offline()` | Done — tested. The whole file is over budget, so every question is refused here until R1–R6 exist |
| 3b | **Budget check, Claude tokenizer** — recount with `messages.count_tokens`; refuse if over | `ask_claude()` | Done — tested with a mocked API; `[PENDING: first live count_tokens figure]` |
| 4 | **Ask Claude** — `claude-opus-5`, adaptive thinking at low effort, `max_tokens` = output budget | `ask_claude()` | Done — `[PENDING: first live answer; needs ANTHROPIC_API_KEY and R1–R6]` |
| 5 | **Report usage** — actual tokens against the budget and as a % of baseline; warns if the answer was cut off | `main()` | Done — tested with a mocked API |
| 6 | **Audit answers** — grade answers with the same columns as the pilot audit and compare | — | `[PLACEHOLDER: not automated; re-audit pending]` |

### Retrieval stages

| # | Stage | What it must do | Status |
| --- | --- | --- | --- |
| R1 | **Chunk** | Split the source into function/class-level chunks, each with its line range. | `[PLACEHOLDER]` |
| R2 | **Index** | Build a searchable index over the chunks (method `[PLACEHOLDER: keyword/BM25 or embeddings — to be chosen]`). | `[PLACEHOLDER]` |
| R3 | **Retrieve** | Rank chunks against the question and take the top-k (`k` = `[PLACEHOLDER]`). | `[PLACEHOLDER]` |
| R4 | **Pack** | Add chunks in rank order until the prompt reaches the 750-token input budget (~640 tokens of code after the system prompt and question). | `[PLACEHOLDER]` |
| R5 | **Cite** | Prompt the model to cite a line range for every claim, and to say "not in the provided code" when the chunks don't answer the question. | `[PLACEHOLDER]` |
| R6 | **Verify citations** | Check each cited line range exists and was in the retrieved context; flag answers with no citation. In the audit, none of the 14 fabricated answers cited the file. | `[PLACEHOLDER]` |

## Token count for `client.py`

| Measurement | `cl100k_base` (GPT-4 / GPT-3.5) | `o200k_base` (GPT-4o) |
| --- | --- | --- |
| `client.py` alone — **the baseline** | **3,940** | **3,945** |
| System prompt + wrapped file (the whole-file bot's fixed prompt) | 3,997 | 4,002 |

These are OpenAI tokenizer counts. Claude uses its own tokenizer, which is why stage 3b recounts
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
  baseline: 3940 tokens (whole client.py, cl100k_base)
  per-question budget: 1150 tokens = 750 input + 400 output (29.2% of baseline; cap is 30%)

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

**Hard budget: 1,150 tokens per question — 29.2% of the baseline.**

The baseline is 3,940 tokens: the whole `client.py` in `cl100k_base`, which the whole-file bot
sends with every question before it has read the question or written a word. That is a
conservative baseline, because it leaves out the whole-file bot's system prompt and its output.
Measured against the audit's own recorded figure for `client.py` (18,742), the budget would be 6.1%.

| Part | Budget | % of 3,940 baseline | How it's enforced |
| --- | --- | --- | --- |
| Input: system prompt + retrieved code + question | **750** | 19.0% | Stage 3a counts the prompt with tiktoken and refuses before any API call; stage 3b recounts with Claude's tokenizer and refuses if over. |
| Output: thinking + answer | **400** | 10.2% | Passed as `max_tokens`, so the API stops generating at 400. Low effort keeps thinking short. Stage 5 warns if an answer was cut off. |
| **Total** | **1,150** | **29.2%** | Stage 5 prints actual usage as a % of baseline after every answer. |

- **The 30% cap is enforced in code.** `code_help_bot.py` asserts at import that the budget is under 30% of the baseline, so a later edit that raises it past 1,182 tokens fails immediately.
- **How the 750 input tokens split:** the system prompt and file wrapper take 57 tokens. The pilot's questions measure 8–13 tokens, so 750 leaves room for a longer question plus about 640 tokens of retrieved code. That is about 16% of `client.py`, or 3–4 functions.
- **Why 400 output tokens:** every answer in the audit was a short API answer, such as a parameter, an exception or a function name. 400 tokens is enough for that plus a line citation and a short snippet.
- **Still unmeasured:** whether 400 is enough once thinking is included: `[PENDING: first live run — rate of stop_reason "max_tokens"]`.

## Audit results — `pilot_answer_audit.xlsx`

The paused whole-file pilot in #developers, 2025-02-03 to 2025-03-06. Figures are from
`evidence/audit_figures.txt`; rerun them with `python evidence/audit_figures.py pilot_answer_audit.xlsx`.

| Figure | Value |
| --- | --- |
| Questions audited | 24 |
| Answers grounded in the source file | 10 (42%) |
| Answers with a fabricated detail an engineer had to correct | **14 (58%)** |
| Answers that cited where in the file | 5 (21%) |
| Fabricated answers that cited where in the file | **0 of 14** |
| Engineer time spent correcting | 235 min (16.8 min per fabrication) |
| Prompt tokens sent, as recorded in the audit | 287,851 total; mean 11,994 per question |

| Source file sent | Questions | Fabricated | Cited | Correction minutes |
| --- | --- | --- | --- | --- |
| `client.py` | 11 | 8 | 2 | 130 |
| `api_endpoints.py` | 6 | 4 | 0 | 70 |
| `helpers.py` | 4 | 2 | 2 | 35 |
| `errors.py` | 3 | 0 | 1 | 0 |

### One fabrication, checked against the file

Audit row 3, question "Can I set a per-request timeout?", sent `client.py`:

> **Bot answered:** "Claimed Client() takes timeout_ms as a (connect, read) tuple"
> **Correction:** "Invented the tuple form for timeout_ms; the file only accepts a single integer" — 25 minutes to correct

This is still false for the `client.py` in this repo. `timeout_ms` is declared as `timeout_ms: int = DEFAULT_TIMEOUT_MS`
(line 89) and used once, as `httpx.Timeout(timeout=self.options.timeout_ms / 1_000)` (line 150).
That is a single number of milliseconds, with no tuple form. The answer was also uncited, like all
14 fabrications. Stages R5–R6 target exactly that pattern.

### Problems with the audit data

- **The token column doesn't match the files it names.** At the upstream commit in use when the pilot started (`1fb34b5`), `client.py` is 1,681 cl100k tokens, but the audit records 18,742. That is 11.1× too high. The other files are off by different factors: `api_endpoints.py` 3.6×, `helpers.py` 4.7×, `errors.py` 2.8×. So the gap isn't a fixed prompt overhead. The sheet doesn't say what else was sent, so I don't use this column as the baseline: `[PENDING: what the pilot's prompt contained besides the file]`. Evidence: `evidence/pilot_upstream_check.txt`.
- **The pilot's `client.py` is an older version than the one in this repo.** For example, automatic retries were added upstream on 2026-03-17 (`3bb5e90`). So row 4's correction, "the file has no retry logic at all", was right for the pilot's file but is wrong for this repo's `client.py`. Fabrication findings from the audit need rechecking against the pinned file before anyone reuses them as test cases.
- **At least one correction is itself wrong.** Row 16 says the bot "invented" a `log_level` option. But `log_level: int = logging.WARNING` exists in both versions of `client.py` (line 50 in the pilot's, line 91 in this repo's). Only the bot's claimed default, DEBUG, was wrong.

## Usage

```bash
pip install -r requirements.txt
python code_help_bot.py --count-only
export ANTHROPIC_API_KEY=...
python code_help_bot.py "Can I set a per-request timeout?"
python code_help_bot.py -f some_other_file.py "Explain this file"
```

Until retrieval stages R1–R6 are built, asking about `client.py` stops at stage 3a, because the
whole file (about 4,000 tokens with a question) is over the 750-token input budget. A file small enough
to fit the budget can already be asked about end to end.
