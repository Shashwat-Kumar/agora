import argparse, json, sys
from pathlib import Path
from .llm import ChatClient, MockClient
from .orchestrator import load_topics, run_thread, topic_for_week
from .protocol import parse_issue_body, validate, to_turn
from .quality import publication_errors

def main(argv=None):
    ap = argparse.ArgumentParser(prog="agora")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="Run this week's thread"); r.add_argument("--provider"); r.add_argument("--mock", action="store_true")
    r.add_argument("--topic"); r.add_argument("--turns", type=int, default=20); r.add_argument("--out", default="threads")
    q = sub.add_parser("check", help="Check whether a live discussion is safe to publish"); q.add_argument("file")
    v = sub.add_parser("validate", help="Validate an outside-agent submission (JSON file or issue body)"); v.add_argument("file")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        errors = publication_errors(json.loads(Path(a.file).read_text()))
        if errors:
            print("\\n".join(errors))
            return 1
        print("PASS: structurally publishable (not fact-checked)")
        return 0
    if a.cmd == "run":
        topics = load_topics()
        topic = next((t for t in topics if t["id"] == a.topic), None) or topic_for_week(topics)
        client = MockClient() if a.mock else ChatClient.from_env(a.provider)
        th = run_thread(client, topic, a.turns)
        if not a.mock:
            errors = publication_errors(th, expected_turns=a.turns)
            if errors:
                print("Run rejected; nothing saved:\\n" + "\\n".join(errors), file=sys.stderr)
                return 1
        p = Path(a.out) / f"{th['generated']}-{topic['id']}.json"; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(th, indent=1, ensure_ascii=False))
        print(p); return 0
    known = {json.loads(f.read_text())["id"] for f in Path("threads").glob("*.json")}
    sub_ = parse_issue_body(Path(a.file).read_text())
    ok, errs = validate(sub_, known)
    print("OK" if ok else "\n".join(errs)); return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
