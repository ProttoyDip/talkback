# End-to-end run: talkback-voice

2026-10-11 · commit `7fb87ad` · 3 run(s) per scenario

| Latency (warm) | p50 | p95 | runs |
|---|---|---|---|
| Spoken question → first audio | 2404 ms | 2499 ms | 3 |
| Typed question → first audio | 1294 ms | 1321 ms | 3 |
| "Wait, stop" → audio stops | 1639 ms | 1731 ms | 3 |

| Recovery | passed |
|---|---|
| Stops when interrupted | 3 of 3 |
| Keeps talking through "uh-huh" | 3 of 3 |
| Correction during a confirmation | 3 of 3 |
| "Never mind" during a tool call | 3 of 3 |

Outdated actions (a corrected change that happened anyway): **0**

## Every run

| Scenario | OK | ms | Note |
|---|---|---|---|
| question | yes | 2404 |  |
| typed | yes | 1294 |  |
| barge_in | yes | 981 |  |
| backchannel | yes |  |  |
| correction | yes |  |  |
| cancel_tool | yes |  |  |
| question | yes | 2499 |  |
| typed | yes | 1249 |  |
| barge_in | yes | 1731 |  |
| backchannel | yes |  |  |
| correction | yes |  |  |
| cancel_tool | yes |  |  |
| question | yes | 2316 |  |
| typed | yes | 1321 |  |
| barge_in | yes | 1639 |  |
| backchannel | yes |  |  |
| correction | yes |  |  |
| cancel_tool | yes |  |  |
