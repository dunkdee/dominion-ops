"""
vault_reporter.py — Dominion VM Agent → Vault Bridge
Reads pipeline logs and writes structured notes to DominionVault.
Called after each major pipeline run via crontab.
Usage: python vault_reporter.py --pipeline <name>
"""
import sys, os, json, argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path.home() / "buddy_core"))
from vault_io import write_note

LOGS = Path.home() / "logs"
SURPLUS_LOGS = Path.home() / "surplus_recovery" / "logs"
DOMINION_LOGS = Path("/var/log/dominion")

def tail(path, n=20):
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except:
        return f"(log not found: {path})"

def report_proposals():
    log = tail(DOMINION_LOGS / "proposals.log", 30)
    submitted = log.count("SAVED") + log.count("DONE")
    errors = log.count("ERROR") + log.count("error")
    write_note(
        title=f"PPH Proposals — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        body=f"## Proposal Run\n\n```\n{log}\n```\n\n**Submitted:** {submitted} | **Errors:** {errors}",
        lane="inbox",
        tags=["proposals", "pph", "revenue"]
    )
    print(f"[VAULT] Proposals note written. Submitted={submitted}")

def report_content():
    log = tail(LOGS / "multi_content.log", 20)
    slots = log.count("Done. Slot")
    write_note(
        title=f"Content Generated — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        body=f"## Content Generation Run\n\n```\n{log}\n```\n\n**Slots completed:** {slots}",
        lane="inbox",
        tags=["content", "social", "pipeline"]
    )
    print(f"[VAULT] Content note written. Slots={slots}")

def report_social():
    log = tail(LOGS / "social_poster.log", 20)
    posted = sum(1 for l in log.splitlines() if "POSTED" in l or "SUCCESS" in l)
    staged = sum(1 for l in log.splitlines() if "STAGED" in l)
    write_note(
        title=f"Social Poster — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        body=f"## Social Poster Run\n\n```\n{log}\n```\n\n**Posted:** {posted} | **Staged:** {staged}",
        lane="inbox",
        tags=["social", "posting", "pipeline"]
    )
    print(f"[VAULT] Social note written. Posted={posted} Staged={staged}")

def report_youtube():
    log = tail(LOGS / "youtube_upload.log", 15)
    uploaded = sum(1 for l in log.splitlines() if "UPLOADED" in l)
    errors = sum(1 for l in log.splitlines() if "ERROR" in l or "403" in l)
    write_note(
        title=f"YouTube Upload — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        body=f"## YouTube Upload Run\n\n```\n{log}\n```\n\n**Uploaded:** {uploaded} | **Errors:** {errors}",
        lane="inbox",
        tags=["youtube", "video", "pipeline"]
    )
    print(f"[VAULT] YouTube note written. Uploaded={uploaded}")

def report_surplus():
    outreach = tail(SURPLUS_LOGS / "outreach.log", 15)
    trace = tail(SURPLUS_LOGS / "trace.log", 10)
    sent = sum(1 for l in outreach.splitlines() if "SENT" in l or "sent" in l)
    write_note(
        title=f"Surplus Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        body=f"## Surplus Outreach\n\n```\n{outreach}\n```\n\n## Skip Trace\n\n```\n{trace}\n```\n\n**Emails sent:** {sent}",
        lane="surplus",
        tags=["surplus", "outreach", "revenue"]
    )
    print(f"[VAULT] Surplus note written. Sent={sent}")

def report_sentinel():
    try:
        status = json.loads((Path.home() / "buddy_core" / "sentinel_status.json").read_text())
        healthy = status.get("healthy", False)
        issues = status.get("open_issues", [])
        fixes = status.get("total_auto_fixes", 0)
        body = f"## Sentinel Health Check\n\n"
        body += f"**Healthy:** {'YES' if healthy else 'NO'}\n"
        body += f"**Auto-fixes:** {fixes}\n\n"
        if issues:
            body += "### Open Issues\n" + "\n".join(f"- {i}" for i in issues)
        else:
            body += "### No open issues"
        write_note(
            title=f"Sentinel Status — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            body=body,
            lane="_health",
            tags=["sentinel", "health", "system"]
        )
        print(f"[VAULT] Sentinel note written. Healthy={healthy}")
    except Exception as e:
        print(f"[VAULT] Sentinel report failed: {e}")

def report_wholesale():
    log = tail(LOGS / "re_scout.log", 15)
    leads = sum(1 for l in log.splitlines() if "lead" in l.lower() or "SAVED" in l)
    write_note(
        title=f"RE Scout — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        body=f"## Real Estate Scout Run\n\n```\n{log}\n```\n\n**Leads found:** {leads}",
        lane="deals",
        tags=["real-estate", "wholesale", "leads"]
    )
    print(f"[VAULT] RE Scout note written. Leads={leads}")

PIPELINES = {
    "proposals": report_proposals,
    "content":   report_content,
    "social":    report_social,
    "youtube":   report_youtube,
    "surplus":   report_surplus,
    "sentinel":  report_sentinel,
    "wholesale": report_wholesale,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", required=True, choices=list(PIPELINES.keys()) + ["all"])
    args = parser.parse_args()

    if args.pipeline == "all":
        for name, fn in PIPELINES.items():
            try:
                fn()
            except Exception as e:
                print(f"[VAULT] {name} failed: {e}")
    else:
        PIPELINES[args.pipeline]()
