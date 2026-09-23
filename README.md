# code-help-bot

A small bot pipeline: take a source file, count its tokens with
[tiktoken](https://github.com/openai/tiktoken), then send it to Claude with a question.

## Files

| File | What it is |
| --- | --- |
| `client.py` | Downloaded verbatim from [ramnes/notion-sdk-py](https://github.com/ramnes/notion-sdk-py) — `notion_client/client.py` at commit `a94e6dfe47f8a44cf642fa6bb7d6c4e6f8468108` (MIT license, © Guillaume Gelin — see `LICENSE-notion-sdk-py`). SHA-256 `95e5aa4fdfd8616d047124ac096e3be708223809f91804839a38483204e9eeb5`. |
| `code_help_bot.py` | Counts the file's tokens, then asks Claude (`claude-opus-5`) your question about it. |

## Token count for `client.py`

Measured by running tiktoken 0.14.0 on the file (18,097 characters, 513 lines):

| Encoding | Tokens |
| --- | --- |
| `cl100k_base` (GPT-4 / GPT-3.5) | **3,940** |
| `o200k_base` (GPT-4o) | **3,945** |

These are OpenAI tokenizer counts. Claude uses its own tokenizer, so the tokens Claude bills for this file will differ; use the API's `messages.count_tokens` endpoint for that number.

## Usage

```bash
pip install -r requirements.txt
python code_help_bot.py --count-only
export ANTHROPIC_API_KEY=...
python code_help_bot.py "How does the retry logic in client.py work?"
python code_help_bot.py -f some_other_file.py "Explain this file"
```
