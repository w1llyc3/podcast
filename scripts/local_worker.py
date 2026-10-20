"""Windows local worker: download new queued episodes, full transcript, readable PDF.
Does not publish copyrighted audio/transcripts to the public GitHub repo.
"""
import argparse, hashlib, json, os, re, sys
from pathlib import Path
from urllib.parse import quote
import requests
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from faster_whisper import WhisperModel

QUEUE_URL = "https://raw.githubusercontent.com/w1llyc3/podcast/main/queue/state.json"
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

def safe_filename(s):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .")[:100] or "episode"

def draw_pdf(path, title, chunks):
    c = canvas.Canvas(str(path), pagesize=A4); w, h = A4
    page = 1; y = h - 62
    def footer():
        c.setFont("STSong-Light", 8);c.setFillGray(.5)
        c.drawString(48, 34, "完整文字稿 · 无时间线")
        c.drawRightString(w-48, 34, f"第 {page} 页")
    def write(s, size=11, leading=20):
        nonlocal y, page
        line = ""
        for ch in s:
            if pdfmetrics.stringWidth(line+ch,"STSong-Light",size) > w-100 and line:
                if y < 72:
                    footer();c.showPage();page+=1;y=h-56
                c.setFillGray(.12);c.setFont("STSong-Light",size);c.drawString(50,y,line)
                y-=leading;line=""
            line+=ch
        if line:
            if y < 72:
                footer();c.showPage();page+=1;y=h-56
            c.setFillGray(.12);c.setFont("STSong-Light",size);c.drawString(50,y,line)
            y-=leading
    write(title, 16, 26);y-=18
    for chunk in chunks:
        chunk=re.sub(r"^\s*\[\d\d?:\d\d(?::\d\d)?\]\s*", "", chunk).strip()
        if not chunk: continue
        write(chunk);y-=12
    footer();c.save()

def download(url, path):
    with requests.get(url, stream=True, timeout=(15,120)) as r:
        r.raise_for_status()
        with path.open("wb") as f:
            for block in r.iter_content(1048576):
                if block:f.write(block)
    if path.stat().st_size < 1024: raise RuntimeError("Empty audio download")

def run(output, model_name, max_items):
    output.mkdir(parents=True, exist_ok=True)
    donefile=output/"completed.json"
    completed=json.loads(donefile.read_text(encoding="utf-8")) if donefile.exists() else {}
    response=requests.get(QUEUE_URL,timeout=35);response.raise_for_status()
    queue=response.json().get("pending",[])
    todo=[x for x in queue if x["key"] not in completed][:max_items]
    if not todo:
        print("No new episodes. If RSS Watch has not run yet, run it once on GitHub.")
        return
    model=WhisperModel(model_name,device="cpu",compute_type="int8")
    for item in todo:
        uid=hashlib.sha256(item["key"].encode()).hexdigest()[:12]
        dest=output/safe_filename(item["feed_name"])/(uid+"_"+safe_filename(item["title"]))
        dest.mkdir(parents=True,exist_ok=True)
        if not item.get("audio_url"):
            print("No public audio URL; skipped", item["title"])
            continue
        audio=dest/"audio.m4a"
        if not audio.exists():download(item["audio_url"],audio)
        segments, info=model.transcribe(str(audio),language="zh",vad_filter=True,beam_size=5)
        chunks=[s.text.strip() for s in segments if s.text.strip()]
        if not chunks:raise RuntimeError("Transcription empty: "+item["title"])
        (dest/"transcript.txt").write_text("\n\n".join(chunks)+"\n",encoding="utf-8")
        draw_pdf(dest/"transcript.pdf",item["title"],chunks)
        (dest/"metadata.json").write_text(json.dumps(item,ensure_ascii=False,indent=2),encoding="utf-8")
        (dest/"summary.md").write_text("# "+item["title"]+"\n\n待生成经校对的学习总结。\n",encoding="utf-8")
        completed[item["key"]]={"path":str(dest),"title":item["title"]}
        donefile.write_text(json.dumps(completed,ensure_ascii=False,indent=2),encoding="utf-8")
        print("Completed:",item["title"])
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default=str(Path.home()/"Podcast Library"))
    ap.add_argument("--model",default="small")
    ap.add_argument("--max-items",type=int,default=3)
    a=ap.parse_args();run(Path(a.output),a.model,a.max_items)
