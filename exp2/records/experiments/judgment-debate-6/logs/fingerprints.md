# jd6 — jd3-main fingerprints

`find outputs/experiments/jd3-main -type f | sort | xargs sha256sum | sha256sum`

| when | sha256 |
|---|---|
| before the smoke (2026-08-30T00:57:11Z) | `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` |
| after the smoke (2026-08-30T01:34:17Z) | `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` |

The two halves of the jd6 prompt smoke — `jd6-smoke-round` (6 cells, rerule +
ruling_agreement + analyse) and `jd6-smoke-plain` (3 cells, rejudge + analyse) — read
`outputs/experiments/jd3-main` and wrote nothing into it. The two hashes above are
identical, and equal to what the tree has hashed to since judgment-debate-3 finished.

`find outputs/experiments/jd3-main -type f | sort | xargs sha256sum | sha256sum`

| BEFORE THE RUN (2026-08-30T02:27:58Z) | `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` |

The two arms of judgment-debate-6 launch from here. `jd3-main` is read by both and
written by neither; the driver halts before spending anything if this hash is not the
one PREREG.md registers.
