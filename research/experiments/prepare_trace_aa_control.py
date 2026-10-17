"""Derive bounded A/A control from the reviewed v3 runner, without editing it."""
from pathlib import Path

root = Path('/home/dcl/projects/llm-serving-benchmark-lab/research/experiments')
source = (root/'run_trace_revalidation_v3.py').read_text().replace('traced', 'arm_b')
replacements = [
    ("'trace-revalidation-v3-'", "'trace-aa-control-'"),
    ("('on' if arm_b else 'off')", "('B' if arm_b else 'A')"),
    ("argv = command+(sum(old.FLAGS.values(), []) if arm_b else [])", "argv = list(command)  # identical in A and B; trace OFF in both"),
    ("directory.name+'-warm',arm_b,rate=4", "directory.name+'-warm',False,rate=4"),
    ("f'{directory.name}-e{episode}',arm_b,rate=4", "f'{directory.name}-e{episode}',False,rate=4"),
    ("assert arm_b or all(r['native_metrics'] is None for r in rr)", "assert all(r['native_metrics'] is None for r in rr)"),
    ("variant='full' if arm_b else 'off'", "variant='B' if arm_b else 'A'"),
    ("old.compare(rows,'off','full'); write(out/'comparison.json',comparison)", "old.compare(rows,'A','B')\n            for value in comparison.values():\n                value['median_absolute_deviation_percent'] = statistics.median(abs(x) for x in value['paired_overhead_percent'])\n            write(out/'comparison.json',comparison)"),
    ("v['median_overhead_percent']<5", "v['median_absolute_deviation_percent']<5"),
    ("all(p<5 for p in v['paired_overhead_percent'])", "all(abs(p)<5 for p in v['paired_overhead_percent'])"),
    ("for arm in ('off','full')", "for arm in ('A','B')"),
    ("all_pairs_below_five=stable_pairs", "all_absolute_pairs_below_five=stable_pairs"),
    ("all five median paired overhead percentages <5", "all five median absolute paired deviations <5; signed deviations also retained"),
    ("every paired overhead <5", "every absolute paired deviation <5"),
    ("single remediation only; stats enabled in both arms; no matrix or component expansion", "A/A negative control: trace disabled and identical argv/env/payload in A and B; stats enabled in both; order A-B B-A A-B; signed B/A changes are variation, not trace overhead"),
]
for before, after in replacements:
    assert source.count(before) == 1, (before, source.count(before))
    source = source.replace(before, after)
assert 'old.FLAGS' not in source
assert "'-warm',arm_b" not in source and '},arm_b,rate=4' not in source
source = '# A/A derivation; see prepare_trace_aa_control.py for exact v3 changes.\n'+source
(root/'run_trace_aa_control.py').write_text(source)
print('A/A runner generated; both server argv and request trace flags fixed identical/OFF')
