# jd3-main (M0) — hand check: 20 Maverick judgments beside their transcripts (Fable, 2026-08-28)

Drawn by `records/derivations/jd3-pilot-handread.py --tree outputs/experiments/jd3-main
--judgments 20`: 10 where Maverick and nano disagree, 10 where they agree. The picker
orders by cell id, so all 20 are gpqa; the pilot's 10 (five subsets) are the cross-check.

**Every judgment is a judgment of the debate.** Each summarises what Alice and Bob argued,
names the point of contention ("the key issue is whether…"), applies the flaw definition
in its own words ("a flaw is a statement or inference that is untrue, illogical, or
misleading"; "whether the flawed statement makes a claim false or an inference invalid"),
and ends on one Verdict line. 0 truncations, 0 repairs, all `strict`. It does re-derive
object-level facts where the debate turns on them (gpqa-111: "in the |up>,|down> basis A's
matrix elements correspond to Sx"; gpqa-102: the directing effects of acetyl and bromine),
which is a judge weighing the arguments rather than re-solving from scratch — the
derivation is used to decide between the debaters, and the debaters are named.

**Accuracy in the sample: 15/20.** Where the judges disagree Maverick is right 9/10 (wrong
on gpqa-10-flawed: accepts Alice's "not strictly linearly correlated" as a fair rejection).
Where they agree it is right 6/10; the four shared errors (gpqa-100-sound, 101-sound,
104-sound, 106-sound) are all SOUND items called FLAWED because a categorical or loosely
worded statement was read as untrue ("a strong acid catalyst is required"; "20% filling
factor" read as global) — the same hedge/threshold question that dominates the audit.

**What the judgments look like from the auditor's side.** They hedge in the open —
"technically incorrect, but…", "can be seen as potentially misleading, but…" — and they
commit to a reading of the definition ("does not necessarily make the text flawed under
the given definition"). That is what makes them auditable, and it is what the audit then
turns against them.
