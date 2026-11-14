import argparse,sys

from .viewer import print_trace
from .client import AgentBench, AgentBenchError

def main(argv=None):
    p = argparse.ArgumentParser(prog="agentbench")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--api-key")

    sub = p.add_subparsers(dest="cmd", required=True)
    show = sub.add_parser("show",help="print one trace as a tree")
    show.add_argument("trace_id")

    args = p.parse_args(argv)
    client = AgentBench(args.base_url, args.api_key)

    try:
        trace = client.get_trace(args.trace_id)
    except AgentBenchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print_trace(trace)
    return 0

if __name__=='__main__':
    raise SystemExit(main(sys.argv[1:]))