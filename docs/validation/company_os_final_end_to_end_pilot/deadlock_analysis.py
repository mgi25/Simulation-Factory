"""Prove the stop is structural, not an artifact of how the request was written."""
import sys, json, datetime as dt
sys.path.insert(0, ".")
from pathlib import Path
from company.engineering.intake import CEORequest, IntakeOutcome, assess_request
from company.runtime.config import load_company_config

DAY = dt.date(2026, 9, 20)
REPO = Path(".").resolve()
cfg = load_company_config(None)
base = json.load(open("docs/evidence/company_os_final_end_to_end_pilot/work_order_request.json",
                      encoding="utf-8"))


def run(objective, rid):
    d = dict(base)
    d["objective"] = objective
    d["request_id"] = rid
    a = assess_request(CEORequest.from_mapping(d), cfg.permissions,
                       repo_root=REPO, authorized_on=DAY)
    return a.outcome.value, [x.reason for x in a.decisions]


title = base["objective"]
out = {}
out["as_selected"] = {
    "objective": title,
    "outcome": run(title, "wo-deadlock-as-selected")[0],
    "reasons": run(title, "wo-deadlock-as-selected")[1],
    "note": "the candidate title, verbatim, exactly as planning produced it",
}

# What the trigger actually is. Not applied - demonstrated, so the report can
# say which word causes it without anybody being tempted to delete that word.
probe = title.replace("credential ", "")
o, r = run(probe, "wo-deadlock-probe-noword")
out["counterfactual_word_removed"] = {
    "objective": probe,
    "outcome": o,
    "reasons": r,
    "note": ("DIAGNOSTIC ONLY, NOT USED. Removing the word 'credential' from a "
             "candidate that exists to fix credential screening would be a "
             "wording hack, which this pilot forbids. Shown so the cause is "
             "named precisely."),
}

# Is the screening actually negation-blind, i.e. is the candidate's own claim true?
for text, key in [
    ("Refactor the retry helper. This work does not touch credentials.",
     "negated_mention_still_escalates"),
    ("Rotate the production credentials.", "asserted_mention_escalates"),
]:
    o, r = run(text, "wo-deadlock-" + key.replace("_", "-")[:40])
    out[key] = {"objective": text, "outcome": o, "reasons": r}

out["conclusion"] = (
    "Exactly one candidate was planning-eligible and it cannot pass intake, "
    "because screen_credentials matches the bare word 'credential' anywhere in "
    "the objective and the candidate's subject IS credential screening. The "
    "defect blocks the authorization of its own fix. No other candidate is "
    "planning-eligible: two are completed, three are blocked or out of "
    "department, and runner-blocked-attempt-repo-dir fails capsule_owned "
    "because nothing owns tools/. So there is no second candidate for "
    "management to move to, and rewording is forbidden."
)
Path("docs/evidence/company_os_final_end_to_end_pilot/deadlock_analysis.json").write_text(
    json.dumps(out, indent=2) + "\n", encoding="utf-8")
for k, v in out.items():
    if isinstance(v, dict):
        print("%-34s %s" % (k, v["outcome"]))
        for rr in v["reasons"]:
            print("    " + rr)
print("")
print(out["conclusion"])
