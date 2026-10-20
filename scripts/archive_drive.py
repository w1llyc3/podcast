"""Explicit opt-in rclone copy to an already-authorized private Drive remote.
No credentials or Google Cloud resources are created by this script.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

def archive(output,remote,dry_run=True):
    executable=shutil.which('rclone')
    if not executable:raise RuntimeError('rclone is not installed; no upload attempted')
    if not remote or remote.startswith('-') or ':' not in remote:
        raise ValueError('Provide an explicit configured private rclone remote:path')
    root=Path(output).resolve()
    completed=json.loads((root/'completed.json').read_text(encoding='utf-8'))
    for row in completed.values():
        dest=Path(row['path']).resolve()
        relative=dest.relative_to(root)
        args=[executable,'copy',str(dest),remote.rstrip('/')+'/'+relative.as_posix(),'--include','audio.m4a','--include','transcript.raw.json','--include','transcript.txt','--include','transcript.pdf','--include','summary.md','--include','metadata.json']
        if dry_run:args.append('--dry-run')
        subprocess.run(args,check=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',default=r'D:\podcast')
    ap.add_argument('--remote',required=True)
    ap.add_argument('--upload',action='store_true',help='Explicitly copy local private artifacts; default is dry run')
    a=ap.parse_args();archive(a.output,a.remote,not a.upload)
