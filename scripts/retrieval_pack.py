#!/usr/bin/env python3
"""Explicit model pack operations; never invoked by page load or application setup."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.mvp.retrieval_packs import PackManager, REGISTRY


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['status','install','check','remove','manifest'])
    parser.add_argument('--profile',choices=list(REGISTRY))
    parser.add_argument('--cache',help='Private absolute cache outside application files')
    parser.add_argument('--device',choices=['cpu','mps'],default='cpu')
    args=parser.parse_args()
    manager=PackManager(args.cache)
    if args.action=='status': result=manager.status(args.profile) if args.profile else manager.capabilities()
    else:
        if not args.profile: parser.error('--profile required')
        if args.action=='manifest': result=manager.manifest(args.profile)
        elif args.action=='check': result=manager.check_runtime(args.profile,args.device)
        else: result=getattr(manager,args.action)(args.profile)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
