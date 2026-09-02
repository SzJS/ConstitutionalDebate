# Injection instrument — the findings challenger

Detection, restoration and false alarms on findings lists with ONE known edit in them. Every score is a string comparison against the edit the injector recorded; see `scripts/inject_findings.py` and PREREG §instrument.

## Settings

```
{
  "trees": [
    "outputs/experiments/fd1-pilot-weak",
    "outputs/experiments/fd1-pilot-strong"
  ],
  "seed": 0,
  "max_lists": 40,
  "min_findings": 2,
  "min_overlap": 20,
  "variants": [
    "control",
    "flip_k",
    "delete_k",
    "duplicate_k_opposite"
  ],
  "lists_drawn": 40,
  "challenger_calls": 160,
  "stub": false,
  "arms": {
    "fd1-pilot-weak": {
      "config": {
        "debater_model": "deepseek/deepseek-v4-flash-0731",
        "judge_model": "meta-llama/llama-4-maverick",
        "n_rounds": 3,
        "turn_style": "simultaneous",
        "word_limit": 400,
        "debater_temperature": 0.7,
        "judge_temperature": 0.0,
        "max_tokens": 16384,
        "reasoning_effort": "off",
        "judge_cot": true,
        "seed": 0,
        "frequency_penalty": 0.0,
        "max_decision_attempts": 2,
        "generation_max_tokens": 8192,
        "n_critique_rounds": 3,
        "provider_order": {
          "deepseek/deepseek-v4-flash-0731": [
            "gmicloud/fp8",
            "coreweave/fp8"
          ],
          "meta-llama/llama-4-maverick": [
            "digitalocean"
          ]
        },
        "provider_allow_fallbacks": false,
        "judge_form": "findings",
        "extend_rounds": false,
        "debater_model_b": null,
        "critic_model": null,
        "recourse_rounds": 0,
        "recourse_judge_model": "meta-llama/llama-4-maverick",
        "challenger_model": "google/gemini-2.5-flash",
        "challenge_word_limit": null,
        "challenger_reasoning_effort": null,
        "challenger_temperature": 0.7,
        "recourse_form": "third_party",
        "comprehension_model": null,
        "challenger_may_decline": true,
        "challenger_variant": "findings",
        "gatekeeper_model": null
      },
      "client_config": {
        "base_url": "https://openrouter.ai/api/v1",
        "max_concurrency": 16,
        "max_attempts": 4,
        "backoff_base_s": 1.0,
        "backoff_cap_s": 30.0,
        "connect_timeout_s": 15.0,
        "read_timeout_s": 300.0,
        "run_timeout_s": 1800.0,
        "max_runs_in_flight": 8,
        "copy_parent": true
      },
      "usable_lists": 41,
      "losses": {
        "fewer than 2 findings": 19
      }
    },
    "fd1-pilot-strong": {
      "config": {
        "debater_model": "deepseek/deepseek-v4-flash-0731",
        "judge_model": "openai/gpt-5.6-luna-20260709",
        "n_rounds": 3,
        "turn_style": "simultaneous",
        "word_limit": 400,
        "debater_temperature": 0.7,
        "judge_temperature": 0.0,
        "max_tokens": 16384,
        "reasoning_effort": "off",
        "judge_cot": true,
        "seed": 0,
        "frequency_penalty": 0.0,
        "max_decision_attempts": 2,
        "generation_max_tokens": 8192,
        "n_critique_rounds": 3,
        "provider_order": {
          "deepseek/deepseek-v4-flash-0731": [
            "gmicloud/fp8",
            "coreweave/fp8"
          ],
          "openai/gpt-5.6-luna-20260709": [
            "openai"
          ]
        },
        "provider_allow_fallbacks": false,
        "judge_form": "findings",
        "extend_rounds": false,
        "debater_model_b": null,
        "critic_model": null,
        "recourse_rounds": 0,
        "recourse_judge_model": "openai/gpt-5.6-luna-20260709",
        "challenger_model": "google/gemini-2.5-flash",
        "challenge_word_limit": null,
        "challenger_reasoning_effort": null,
        "challenger_temperature": 0.7,
        "recourse_form": "third_party",
        "comprehension_model": null,
        "challenger_may_decline": true,
        "challenger_variant": "findings",
        "gatekeeper_model": null
      },
      "client_config": {
        "base_url": "https://openrouter.ai/api/v1",
        "max_concurrency": 16,
        "max_attempts": 4,
        "backoff_base_s": 1.0,
        "backoff_cap_s": 30.0,
        "connect_timeout_s": 15.0,
        "read_timeout_s": 300.0,
        "run_timeout_s": 1800.0,
        "max_runs_in_flight": 8,
        "copy_parent": true
      },
      "usable_lists": 26,
      "losses": {
        "fewer than 2 findings": 34
      }
    }
  }
}
```

## Losses in the source trees

- `fd1-pilot-weak`: 41 usable lists; excluded — fewer than 2 findings: 19
- `fd1-pilot-strong`: 26 usable lists; excluded — fewer than 2 findings: 34

## Results

### fd1-pilot-weak

| variant | n | detected | restored (of detected) | false alarms (control) | net |
|---|---|---|---|---|---|
| `flip_k` | 20 |  12/20   60.0%  [38.7,  78.1] |  11/11  100.0%  [74.1, 100.0] |   9/20   45.0%  [25.8,  65.8] | +3 |
| `delete_k` | 20 |   6/20   30.0%  [14.5,  51.9] |   3/5    60.0%  [23.1,  88.2] |   1/20    5.0%  [ 0.9,  23.6] | +5 |
| `duplicate_k_opposite` | 20 |  20/20  100.0%  [83.9, 100.0] |  11/20   55.0%  [34.2,  74.2] |   0/20    0.0%  [ 0.0,  16.1] | +20 |

Detected but no ruling came back: 2 (counted out of the restoration denominator, not as a failure to restore).

### fd1-pilot-weak — the challenger on unaltered lists (control arm)

- lists: 20; stances: contests=16, declined=4
- contests parsed: 26 (finding 24, omission 2, contradiction 0)
- contests per objection that raised one: 1.62
- void:   0/26    0.0%  [ 0.0,  12.9]

### fd1-pilot-strong

| variant | n | detected | restored (of detected) | false alarms (control) | net |
|---|---|---|---|---|---|
| `flip_k` | 20 |  18/20   90.0%  [69.9,  97.2] |  13/17   76.5%  [52.7,  90.4] |   2/20   10.0%  [ 2.8,  30.1] | +16 |
| `delete_k` | 20 |  12/20   60.0%  [38.7,  78.1] |   3/12   25.0%  [ 8.9,  53.2] |   1/20    5.0%  [ 0.9,  23.6] | +11 |
| `duplicate_k_opposite` | 20 |  17/20   85.0%  [64.0,  94.8] |  14/17   82.4%  [59.0,  93.8] |   0/20    0.0%  [ 0.0,  16.1] | +17 |

Detected but no ruling came back: 1 (counted out of the restoration denominator, not as a failure to restore).

### fd1-pilot-strong — the challenger on unaltered lists (control arm)

- lists: 20; stances: contests=9, declined=11
- contests parsed: 10 (finding 8, omission 2, contradiction 0)
- contests per objection that raised one: 1.11
- void:   1/10   10.0%  [ 1.8,  40.4]

### pooled (both arms)

| variant | n | detected | restored (of detected) | false alarms (control) | net |
|---|---|---|---|---|---|
| `flip_k` | 40 |  30/40   75.0%  [59.8,  85.8] |  24/28   85.7%  [68.5,  94.3] |  11/40   27.5%  [16.1,  42.8] | +19 |
| `delete_k` | 40 |  18/40   45.0%  [30.7,  60.2] |   6/17   35.3%  [17.3,  58.7] |   2/40    5.0%  [ 1.4,  16.5] | +16 |
| `duplicate_k_opposite` | 40 |  37/40   92.5%  [80.1,  97.4] |  25/37   67.6%  [51.5,  80.4] |   0/40    0.0%  [ 0.0,   8.8] | +37 |

Detected but no ruling came back: 3 (counted out of the restoration denominator, not as a failure to restore).

### pooled (both arms) — the challenger on unaltered lists (control arm)

- lists: 40; stances: contests=25, declined=15
- contests parsed: 36 (finding 32, omission 4, contradiction 0)
- contests per objection that raised one: 1.44
- void:   1/36    2.8%  [ 0.5,  14.2]

## Spend

$0.5473 over 160 challenger calls and 82 rulings.
