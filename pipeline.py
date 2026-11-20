"""RSS -> full audio -> transcription -> PDF -> persistent cloud archive.

Designed to be re-run; persistent state is held in archive remote, not Actions artifacts.
"""
if __name__ == "__main__":
    raise SystemExit("Legacy cloud pipeline is disabled. Use run-local.ps1 for local processing.")
import json, os, re, subprocess, tempfile, hashlib, shutil
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests
import feedparser
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.pagesizes import A4
from faster_whisper import WhisperModel

REMOTE=os.environ.get("ARCHIVE_REMOTE","podcastdrive:Podcast Library").rstrip("/")
MODEL=os.environ.get("WHISPER_MODEL","small")
EPISODE_ID=os.environ.get("EPISODE_ID","").strip()
FEEDS=json.loads(Path("config/feeds.json").read_text(encoding="utf-8"))
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

def rclone(*args, check=True):
    return subprocess.run(["rclone",*args],check=check,capture_output=True,text=True)

def remote_read(path):
    p=subprocess.run(["rclone","cat",f"{REMOTE}/{path}"],capture_output=True,text=True)
    return p.stdout if p.returncode==0 else None

def remote_write(local, path):
    rclone("copyto",str(local),f"{REMOTE}/{path}")

def download(url, path):
    with requests.get(url,stream=True,timeout=(20,120),headers={"User-Agent":"PodcastPDF/0.1"}) as response:
        response.raise_for_status()
        with path.open("wb") as f:
            for chunk in response.iter_content(1024*1024):
                if chunk:f.write(chunk)
    if path.stat().st_size<1024:raise ValueError("Audio appears empty")

def wrap_by_width(text, font, size, width):
    lines=[];current=""
    for ch in text:
        if pdfmetrics.stringWidth(current+ch,font,size)>width and current:
            lines.append(current);current=ch
        else:current+=ch
    if current:lines.append(current)
    return lines

def pdf_out(title, paragraphs, output):
    c=canvas.Canvas(str(output),pagesize=A4); w,h=A4
    page=1;y=h-64
    def new_page():
        nonlocal page,y
        c.setFont("STSong-Light",8);c.setFillGray(.48)
        c.drawString(50,35,"完整文字稿 · 阅读版");c.drawRightString(w-50,35,f"第 {page} 页")
        c.showPage();page+=1;y=h-55
    def lines(s,size=11,lead=19):
        nonlocal y
        for line in wrap_by_width(s,"STSong-Light",size,w-104):
            if y<70:new_page()
            c.setFont("STSong-Light",size);c.setFillGray(.12);c.drawString(52,y,line);y-=lead
    lines(title,16,25);y-=12
    for p in paragraphs:
        text=re.sub(r"^\\s*\\[\\d{1,2}:\\d{2}(?::\\d{2})?\\]\\s*","",p).strip()
        if not text:continue
        lines(text);y-=11
    new_page()
    # Avoid leaving a trailing empty page: last showPage() flushes the completed page.
    c.save()

def main():
    model=None
    for feed in FEEDS:
        if not feed.get("enabled"):continue
        fid=feed["id"]
        result=feedparser.parse(feed["rss"],request_headers={"User-Agent":"PodcastPDF/0.1"})
        if not result.entries:raise RuntimeError(f"No RSS entries for {fid}")
        state_path=f"_state/{fid}.json"
        old=remote_read(state_path)
        state=json.loads(old) if old else {"done":{},"baseline":[]}
        if not old and not EPISODE_ID:
            state["baseline"]=[str(e.get("id") or e.get("link")) for e in result.entries]
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/"state.json";p.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
                remote_write(p,state_path)
            print(f"{fid}: baseline initialized ({len(state['baseline'])} entries)")
            continue
        entries=list(reversed(result.entries))
        for e in entries:
            guid=str(e.get("id") or e.get("link") or "")
            if not guid or (EPISODE_ID and EPISODE_ID not in guid):continue
            if guid in state["done"] or (not EPISODE_ID and guid in state.get("baseline",[])):continue
            media=next((x.get("href") for x in e.get("enclosures",[]) if x.get("href")),None)
            if not media:
                print(f"Skip {guid}: RSS missing enclosure");continue
            slug=hashlib.sha256(guid.encode()).hexdigest()[:16]
            root=f"{fid}/{slug}"
            with tempfile.TemporaryDirectory() as td:
                work=Path(td);audio=work/"audio.m4a";download(media,audio)
                if model is None:model=WhisperModel(MODEL,device="cpu",compute_type="int8")
                segments,info=model.transcribe(str(audio),language="zh",vad_filter=True,beam_size=5)
                parts=[s.text.strip() for s in segments if s.text.strip()]
                if not parts:raise RuntimeError(f"Empty transcription: {guid}")
                title=e.get("title",slug)
                txt=work/"transcript.txt";txt.write_text("\n\n".join(parts)+"\n",encoding="utf-8")
                pdf=work/"transcript.pdf";pdf_out(title,parts,pdf)
                meta={"guid":guid,"title":title,"rss":feed["rss"],"original_url":e.get("link",""),"created_at":datetime.now(timezone.utc).isoformat(),"language":info.language,"duration":info.duration}
                (work/"metadata.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
                (work/"summary.md").write_text("# "+title+"\n\n自动学习笔记待生成；请结合全文校对。\n",encoding="utf-8")
                for name in ["audio.m4a","transcript.txt","transcript.pdf","summary.md","metadata.json"]:remote_write(work/name,f"{root}/{name}")
                state["done"][guid]={"path":root,"title":title,"original_url":e.get("link",""),"created_at":meta["created_at"]}
                sp=work/"state.json";sp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
                remote_write(sp,state_path)
                print(f"Archived {title} -> {root}")
if __name__=="__main__":main()
