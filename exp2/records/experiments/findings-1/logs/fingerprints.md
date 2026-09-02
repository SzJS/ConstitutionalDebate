# findings-1 — tree fingerprints

`find <tree> -type f | sort | xargs sha256sum | sha256sum`, the form every
fingerprint in this repo's records uses. `jd3-main` is READ by both arms and
written by neither: it holds the stored debate transcripts both arms re-judge
into findings, and M0's verdicts, which are the accuracy comparator. It must be
identical at every point below, and equal to `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c`.

## before the first arm — 2026-09-02T17:01:34Z
| tree | sha256 |
|---|---|
| `jd3-main` | `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` |

## after the STOP at arm W — 2026-09-02T17:03:40Z
| tree | sha256 |
|---|---|
| `jd3-main` | `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` |

## after arm W — 2026-09-02T18:22:24Z
| tree | sha256 |
|---|---|
| `jd3-main` | `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` |

## after arm S — 2026-09-02T18:42:58Z
| tree | sha256 |
|---|---|
| `jd3-main` | `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` |

## after the last arm — 2026-09-02T18:43:16Z
| tree | sha256 |
|---|---|
| `jd3-main` | `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` |

