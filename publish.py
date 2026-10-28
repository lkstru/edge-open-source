#!/usr/bin/env python3
"""Publish only locally verified, public static artifacts to the approved Pages project."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import collect

ROOT=Path(__file__).resolve().parent
WRANGLER=ROOT/'node_modules/wrangler/bin/wrangler.js'


def local_config():
    config=ROOT/'deploy/project.env'
    values={}
    if config.is_file():
        for line in config.read_text().splitlines():
            key,separator,value=line.partition('=')
            if separator and not key.lstrip().startswith('#'):
                values[key.strip()]=value.strip()
    return values


def configured_project_name(override=None):
    name=override or os.environ.get('PAGES_PROJECT_NAME') or local_config().get('PAGES_PROJECT_NAME')
    if not name or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,57}',name):
        raise SystemExit('Set PAGES_PROJECT_NAME in deploy/project.env (see project.env.example).')
    return name


def validate(folder):
    info=json.loads((folder/'nodes.json').read_text())
    started=datetime.datetime.fromisoformat(info['generated_at'])
    age=datetime.datetime.now(datetime.timezone.utc)-started
    if not datetime.timedelta(minutes=-1) <= age <= datetime.timedelta(minutes=30):
        raise ValueError('Snapshot is stale; re-run local verification before publishing.')
    if any(row.get('rechecked') is not True for row in info['nodes']):
        raise ValueError('Snapshot contains nodes without the required second verification')
    if set(info['countries'])!=set(collect.country_codes()):
        raise ValueError('Incomplete country catalogue')
    if any(not collect.public_endpoint(r['host'],r['port']) or r['protocol'] not in ('http','socks5')
           or r['country'] not in info['countries'] for r in info['nodes']):
        raise ValueError('Invalid public node')
    if (folder/'subscribe.conf').read_text()!=collect.config_text(info['nodes'],info['generated_at']):
        raise ValueError('Subscription does not match verified snapshot')
    expected=set(p.name for p in (ROOT/'web').iterdir())|{'nodes.json','subscribe.conf','countries'}
    if set(p.name for p in folder.iterdir())!=expected:
        raise ValueError('Unexpected files in deployment directory')
    wanted={r['country']+'.conf' for r in info['nodes']}
    if set(p.name for p in (folder/'countries').iterdir())!=wanted:
        raise ValueError('Stale or missing country exports')
    for filename in wanted:
        code=filename[:2]
        if (folder/'countries'/filename).read_text()!=collect.config_text(
                [r for r in info['nodes'] if r['country']==code],info['generated_at']):
            raise ValueError('Country file does not match verified snapshot')
    for asset in (ROOT/'web').iterdir():
        if (folder/asset.name).read_bytes()!=asset.read_bytes():
            raise ValueError('Static asset does not match source: '+asset.name)
    return info


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--countries',default='ALL')
    parser.add_argument('--limit',type=int,default=16)
    parser.add_argument('--project-name',help='Cloudflare Pages project name; defaults to PAGES_PROJECT_NAME')
    parser.add_argument('--branch')
    parser.add_argument('--skip-refresh',action='store_true',help='Publish existing snapshot only if less than 30 minutes old')
    parser.add_argument('--allow-empty',action='store_true',
                        help='Allow publishing an empty REJECT-only snapshot')
    args=parser.parse_args()
    project=configured_project_name(args.project_name)
    branch=args.branch or os.environ.get('PAGES_BRANCH') or local_config().get('PAGES_BRANCH','main')
    if not WRANGLER.exists():
        raise SystemExit('Run npm ci --ignore-scripts in local-proxy-direct first.')
    previous_file=ROOT/'.published-nodes.json'
    baseline=ROOT/'dist/nodes.json'
    if not previous_file.exists() and baseline.exists():
        # Preserve the pre-upgrade baseline before dist can be replaced.
        collect.atomic_write(previous_file,baseline.read_text())
    if not args.skip_refresh:
        subprocess.run([sys.executable,str(ROOT/'collect.py'),'--countries',args.countries,
                        '--limit',str(args.limit),'--workers','8'],check=True)
    snapshot=ROOT/'output/pages/nodes.json'
    try:
        node_count=len(json.loads(snapshot.read_text())['nodes'])
    except (OSError,KeyError,TypeError,json.JSONDecodeError) as error:
        raise SystemExit(f'Cannot read verified snapshot; Pages deployment cancelled: {error}')
    if node_count==0 and not args.allow_empty:
        raise SystemExit(
            'No verified nodes. Pages deployment cancelled; the current online snapshot stays unchanged. '
            'Run again later, or pass --allow-empty to intentionally publish a REJECT-only snapshot.'
        )
    with tempfile.TemporaryDirectory(dir=ROOT,prefix='.publish-') as temp:
        stage=Path(temp)/'pages'
        shutil.copytree(ROOT/'output/pages',stage)
        info=validate(stage)
        # Stable local build directory; Wrangler gets no user node/credential files.
        dist=ROOT/'dist'
        if dist.exists():shutil.rmtree(dist)
        shutil.copytree(stage,dist)
    command=['node',str(WRANGLER),'pages','deploy',str(dist),
             '--project-name',project,'--branch',branch,
             '--commit-message','Publish locally verified static proxy snapshot']
    print(f'Publishing {len(info["nodes"])} verified public nodes; no Cloudflare tunnel.',flush=True)
    subprocess.run(command,cwd=ROOT/'deploy',check=True)
    collect.atomic_write(ROOT/'.published-nodes.json',json.dumps(info,ensure_ascii=False)+'\n')


if __name__=='__main__':
    with (ROOT/'.publish.lock').open('w') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another publish is running.')
        main()
