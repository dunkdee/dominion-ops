#!/usr/bin/env python3
"""Stage 4 local-file historical adapter and non-contact shadow observation CLI."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from control_plane.historical_sources import adapt_historical_snapshot
from control_plane.shadow_observation import run_non_contact_shadow_observation
def load(path:str)->dict:
    value=json.loads(Path(path).read_text())
    if not isinstance(value,dict): raise ValueError(f'{path} must contain a JSON object')
    return value
def emit(value:dict,output:str|None)->None:
    text=json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False)+'\n'
    if output:
        target=Path(output); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(text)
    print(text,end='')
def main()->int:
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    adapt=sub.add_parser('adapt'); adapt.add_argument('--input',required=True); adapt.add_argument('--output')
    observe=sub.add_parser('observe'); observe.add_argument('--snapshot',required=True); observe.add_argument('--envelope',required=True); observe.add_argument('--council-decision',required=True); observe.add_argument('--guardrails',required=True); observe.add_argument('--output')
    args=parser.parse_args()
    if args.command=='adapt': result=adapt_historical_snapshot(load(args.input))
    else:
        result=run_non_contact_shadow_observation(adapted_snapshot=adapt_historical_snapshot(load(args.snapshot)),proposal_envelope=load(args.envelope),council_decision=load(args.council_decision),guardrails=load(args.guardrails))
    emit(result,args.output); return 0
if __name__=='__main__': raise SystemExit(main())
