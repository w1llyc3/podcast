"""Windows local worker: download new queued episodes, full transcript, readable PDF.
Does not publish copyrighted audio/transcripts to the public GitHub repo.
"""
import argparse, hashlib, json, os, re, sys, time, logging, math
from pathlib import Path
import requests
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from filelock import FileLock
import feedparser
import av
import numpy as np
from study_notes import build_notes
import csv, io

QUEUE_URL = "https://raw.githubusercontent.com/w1llyc3/podcast/main/queue/state.json"
FONT = "PodcastChinese"

def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

def sha256_file(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):digest.update(block)
    return digest.hexdigest()

def completed_valid(prior):
    if not prior:return False
    dest=Path(prior['path'])
    if not all((dest/name).is_file() for name in ('audio.m4a','transcript.raw.json','transcript.txt','transcript.pdf','metadata.json','summary.md')):return False
    return all(sha256_file(dest/name)==digest for name,digest in prior.get('hashes',{}).items())

def write_index(output,completed,states):
    rows=[]
    for key,state in states.items():
        row={"key":key,**state}
        if key in completed:
            dest=Path(completed[key]["path"])
            metadata=read_json(dest/"metadata.json",{})
            row.update(title=completed[key]["title"],published=metadata.get("published"),url=metadata.get("url"),summary_status=metadata.get("summary_status"),outputs=metadata.get("outputs",{}))
        rows.append(row)
    atomic_json(output/"index.json",rows)
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=["key","title","status","path","error"])
    writer.writeheader()
    writer.writerows({k:r.get(k,"") for k in writer.fieldnames} for r in rows)
    tmp=output/"index.csv.tmp";tmp.write_text(buf.getvalue(),encoding="utf-8-sig");tmp.replace(output/"index.csv")
    # Local-only outbox. No assertion that ChatGPT can read or receive it.
    atomic_json(output/"notification-outbox.json",[{"key":r["key"],"title":r.get("title"),"status":r["status"],"outputs":r.get("outputs",{}),"delivery_status":"local_only_no_chatgpt_bridge"} for r in rows if r["status"]=="completed"])

def register_font():
    font = Path(os.environ.get("PODCAST_FONT", r"C:\Windows\Fonts\simhei.ttf"))
    if not font.exists():
        raise RuntimeError("Set PODCAST_FONT to a Chinese TrueType font")
    pdfmetrics.registerFont(TTFont(FONT, str(font)))

def safe_filename(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .")[:60] or "episode"
    return "_" + s if s.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1,10)], *[f"LPT{i}" for i in range(1,10)]} else s

def draw_pdf(path, title, chunks, url=""):
    register_font()
    c = canvas.Canvas(str(path), pagesize=A4); w, h = A4
    page = 1; y = h - 62
    def footer():
        c.setFont(FONT, 8);c.setFillGray(.5)
        c.drawString(48, 34, "完整文字稿 · 无时间线")
        c.drawRightString(w-48, 34, f"第 {page} 页")
    def write(s, size=11, leading=20):
        nonlocal y, page
        line = ""
        for ch in s:
            if pdfmetrics.stringWidth(line+ch,FONT,size) > w-100 and line:
                if y < 72:
                    footer();c.showPage();page+=1;y=h-56
                c.setFillGray(.12);c.setFont(FONT,size);c.drawString(50,y,line)
                y-=leading;line=""
            line+=ch
        if line:
            if y < 72:
                footer();c.showPage();page+=1;y=h-56
            c.setFillGray(.12);c.setFont(FONT,size);c.drawString(50,y,line)
            y-=leading
    write(title, 16, 26);y-=18
    if url:
        write(url, 9, 14);y-=12
    for chunk in chunks:
        chunk=re.sub(r"^\s*\[\d\d?:\d\d(?::\d\d)?\]\s*", "", chunk).strip()
        if not chunk: continue
        write(chunk);y-=12
    footer();c.save()

def download(url, path, attempts=3):
    """Keep partial bytes separate; resume only against a matching validator."""
    part = path.with_suffix(path.suffix + ".part")
    receipt = part.with_suffix(".http.json")
    for attempt in range(attempts):
        try:
            saved = read_json(receipt, {})
            offset = part.stat().st_size if part.exists() and saved.get("url") == url and saved.get("validator") else 0
            headers = {"Accept-Encoding": "identity"}
            if offset:
                headers.update({"Range": f"bytes={offset}-", "If-Range": saved["validator"]})
            with requests.get(url, stream=True, timeout=(15,120), headers=headers) as r:
                if r.status_code == 416 and offset:
                    part.write_bytes(b"")
                    atomic_json(receipt,{})
                r.raise_for_status()
                if r.status_code == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", r.headers.get("Content-Range", ""))
                    if not match or int(match[1]) != offset:
                        raise RuntimeError("Invalid HTTP range")
                    expected = int(match[3])
                else:
                    offset = 0
                    expected = int(r.headers.get("Content-Length", 0))
                atomic_json(receipt, {"url":url, "validator":r.headers.get("ETag") or r.headers.get("Last-Modified"), "expected":expected})
                with part.open("ab" if offset else "wb") as f:
                    for block in r.iter_content(262144):
                        if block: f.write(block)
                if part.stat().st_size < 1024 or (expected and part.stat().st_size != expected):
                    raise RuntimeError("Incomplete audio download")
            part.replace(path)
            return
        except (requests.RequestException, OSError, RuntimeError):
            logging.exception("Download attempt %s failed", attempt+1)
            if attempt+1 == attempts: raise
            time.sleep(min(2**attempt, 8))

def decode_audio(path):
    from faster_whisper.audio import decode_audio as decode
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        fmt = container.format.name
        declared = float(stream.duration * stream.time_base) if stream.duration else (container.duration or 0)/av.time_base
    audio = decode(str(path), sampling_rate=16000)
    duration = len(audio)/16000
    if duration <= 0 or not np.isfinite(audio).all(): raise RuntimeError("Invalid decoded audio")
    if declared and abs(duration-declared) > max(2, declared*.01):
        raise RuntimeError(f"Audio duration mismatch: {duration} vs {declared}")
    return audio, {"duration_seconds":duration,"container":fmt,"declared_seconds":declared,"bytes":path.stat().st_size,"sha256":sha256_file(path)}

def select_episode(episode_id, list_only=False):
    feeds = read_json(Path(__file__).resolve().parents[1]/"config/feeds.json", [])
    choices = []
    for feed in feeds:
        if not feed.get("enabled"): continue
        r=requests.get(feed["rss"],timeout=40);r.raise_for_status()
        for e in feedparser.parse(r.content).entries:
            uid=str(e.get("id") or e.get("link"))
            row={"key":feed["id"]+":"+uid,"feed_id":feed["id"],"feed_name":feed["name"],"guid":uid,"title":e.get("title",""),"url":e.get("link",""),"audio_url":next((x.get("href") for x in e.get("enclosures",[]) if x.get("href")),""),"published":e.get("published",""),"rss_duration":e.get("itunes_duration","")}
            if list_only: print(json.dumps(row,ensure_ascii=False))
            if episode_id in (uid,row["key"],row["url"]): choices.append(row)
    if list_only: return []
    if len(choices)!=1: raise ValueError("Episode must match exactly one public RSS GUID or URL")
    return choices

def transcribe_chunks(audio, model, rawfile, fingerprint, chunk_seconds=90):
    raw = read_json(rawfile, {"fingerprint":fingerprint,"chunks":[],"segments":[]})
    if raw["fingerprint"] != fingerprint:
        raise RuntimeError("Checkpoint belongs to different audio/model/settings")
    count = math.ceil(len(audio)/(16000*chunk_seconds))
    for index in range(len(raw["chunks"]), count):
        start=index*chunk_seconds
        piece=audio[start*16000:(start+chunk_seconds)*16000]
        segments, info=model.transcribe(piece,language="zh",vad_filter=True,beam_size=5,condition_on_previous_text=False,initial_prompt=fingerprint.get("initial_prompt"))
        rows=[{"start":start+s.start,"end":start+s.end,"text":s.text.strip(),"avg_logprob":s.avg_logprob,"no_speech_prob":s.no_speech_prob} for s in segments if s.text.strip()]
        raw["segments"].extend(rows)
        raw["chunks"].append({"index":index,"start":start,"end":min(len(audio)/16000,start+chunk_seconds),"segments":len(rows)})
        atomic_json(rawfile,raw)
        logging.info("Transcribed chunk %s/%s",index+1,count)
    raw["complete"]=True
    atomic_json(rawfile,raw)
    return raw

def reading_paragraphs(segments):
    """Group consecutive ASR segments without rewriting any recognized words."""
    paragraphs=[];current=""
    for i,segment in enumerate(segments):
        text=segment["text"]
        separator=" " if current and current[-1].isascii() and text[0].isascii() else ""
        current+=separator+text
        gap=(segments[i+1]["start"]-segment["end"]) if i+1<len(segments) else 0
        if len(current)>=220 or (len(current)>=90 and (re.search(r"[。！？.!?]$",text) or gap>1.2)):
            paragraphs.append(current);current=""
    if current:paragraphs.append(current)
    return paragraphs


def run(output, model_name, max_items, episode_id=None, queue_file=None, attempts=3, reprocess=False):
    output=output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output/"logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s",handlers=[logging.FileHandler(output/"logs"/"worker.log",encoding="utf-8"),logging.StreamHandler()])
    with FileLock(str(output/".worker.lock"), timeout=0):
        return consume(output,model_name,max_items,episode_id,queue_file,attempts,reprocess)


def consume(output,model_name,max_items,episode_id,queue_file,attempts,reprocess=False):
    donefile=output/"completed.json"
    statefile=output/"worker-state.json"
    completed=read_json(donefile,{})
    states=read_json(statefile,{})
    if episode_id:
        queue=select_episode(episode_id)
    elif queue_file:
        queue=read_json(Path(queue_file),{}).get("pending",[])
    else:
        response=requests.get(QUEUE_URL,timeout=35);response.raise_for_status()
        queue=response.json().get("pending",[])
    model=None
    failures=0
    unique={x["key"]:x for x in queue}
    processed=0
    for item in unique.values():
        key=item["key"]
        prior=completed.get(key)
        if not reprocess and completed_valid(prior):
            if not prior.get('hashes'):
                prior['hashes']={name:sha256_file(Path(prior['path'])/name) for name in ('audio.m4a','transcript.raw.json','transcript.txt','transcript.pdf','metadata.json','summary.md')}
                atomic_json(donefile,completed)
            states.setdefault(key,{'attempts':0}).update(status='completed',path=prior['path'],error=None)
            atomic_json(statefile,states)
            logging.info("Already completed; skipped %s",key)
            continue
        if processed >= max_items: break
        processed+=1
        uid=hashlib.sha256(key.encode()).hexdigest()[:12]
        dest=output/safe_filename(item["feed_name"])/(uid+"_"+safe_filename(item["title"]))
        dest.mkdir(parents=True,exist_ok=True)
        if reprocess and (dest/"transcript.raw.json").exists():
            backup=dest/("transcript.raw.backup-"+str(time.time_ns())+".json")
            (dest/"transcript.raw.json").replace(backup)
        for attempt in range(attempts):
            state=states.setdefault(key,{"attempts":0})
            state.update(status="running",path=str(dest),attempts=state["attempts"]+1)
            atomic_json(statefile,states)
            try:
                if not item.get("audio_url"): raise RuntimeError("Missing public audio URL")
                audiofile=dest/"audio.m4a"
                if not audiofile.exists(): download(item["audio_url"],audiofile)
                try:
                    audio,probe=decode_audio(audiofile)
                except Exception:
                    audiofile.replace(dest/("audio.invalid-"+str(time.time_ns())+".m4a"))
                    raise
                duration=item.get("rss_duration", "")
                if duration:
                    parts=[float(x) for x in str(duration).split(":")]
                    expected=sum(x*60**i for i,x in enumerate(reversed(parts)))
                    if abs(probe["duration_seconds"]-expected)>max(3,expected*.01):
                        raise RuntimeError("RSS duration differs from decoded audio; possible preview")
                prompt=f"《{item['feed_name']}》，{item['title']}。以下是简体中文播客逐字稿，包含自然标点。"
                fingerprint={"audio_sha256":probe["sha256"],"model":model_name,"chunk_seconds":90,"language":"zh","beam_size":5,"initial_prompt":prompt}
                rawfile=dest/"transcript.raw.json"
                raw=read_json(rawfile,{})
                if not raw.get("complete"):
                    if model is None:
                        from faster_whisper import WhisperModel
                        model=WhisperModel(model_name,device="cpu",compute_type="int8",download_root=str(output/"models"),cpu_threads=min(os.cpu_count() or 4,8))
                    raw=transcribe_chunks(audio,model,rawfile,fingerprint)
                elif raw.get("fingerprint")!=fingerprint:
                    raise RuntimeError("Completed transcript settings mismatch")
                chunks=reading_paragraphs(raw["segments"])
                if not chunks: raise RuntimeError("Transcription empty")
                text="\n\n".join(chunks)+"\n"
                txt=dest/"transcript.txt"
                tmp=txt.with_suffix(".tmp");tmp.write_text(text,encoding="utf-8");tmp.replace(txt)
                pdf=dest/"transcript.pdf"
                tmp=pdf.with_suffix(".tmp");draw_pdf(tmp,item["title"],chunks,item.get("url",""));tmp.replace(pdf)
                summary=dest/"summary.md"
                tmp=summary.with_suffix(".tmp");tmp.write_text(build_notes(item["title"],chunks,raw["segments"]),encoding="utf-8");tmp.replace(summary)
                atomic_json(dest/"metadata.json",{**item,"audio":probe,"transcription":{"model":model_name,"device":"cpu","compute_type":"int8","complete":True,"chunks":len(raw["chunks"]),"segments":len(raw["segments"]),"paragraphs":len(chunks),"human_reviewed":False,"boundary_note":"Independent 90-second chunks; boundary wording requires review"},"summary_status":"local_extractive_unreviewed","outputs":{"audio":str(audiofile),"txt":str(txt),"pdf":str(pdf),"summary":str(summary)},"completed_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())})
                completed[key]={"path":str(dest),"title":item["title"],"audio_sha256":probe["sha256"],"hashes":{p.name:sha256_file(p) for p in (audiofile,rawfile,txt,pdf,summary,dest/"metadata.json")}}
                atomic_json(donefile,completed)
                state.update(status="completed",error=None)
                atomic_json(statefile,states)
                write_index(output,completed,states)
                logging.info("Completed %s",key)
                break
            except Exception as exc:
                state.update(status="failed",error=f"{type(exc).__name__}: {exc}")
                atomic_json(statefile,states)
                write_index(output,completed,states)
                logging.exception("Episode failed %s attempt %s",key,attempt+1)
                if attempt+1==attempts: failures+=1
                else: time.sleep(min(2**attempt,8))
    logging.info("Batch finished: selected=%s failures=%s",len(unique),failures)
    write_index(output,completed,states)
    return 1 if failures else 0


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default=r"D:\podcast")
    ap.add_argument("--model",default="large-v3-turbo")
    ap.add_argument("--max-items",type=int,default=3)
    ap.add_argument("--episode-id",help="Explicit public RSS GUID or episode URL; never changes cloud baseline")
    ap.add_argument("--list-episodes",action="store_true")
    ap.add_argument("--queue-file",help="Local queue snapshot for offline consumption/testing")
    ap.add_argument("--attempts",type=int,default=3)
    ap.add_argument("--reprocess",action="store_true",help="Explicitly redo selected episodes; preserve previous raw transcript")
    a=ap.parse_args()
    if a.list_episodes: select_episode(None,True)
    else: sys.exit(run(Path(a.output),a.model,a.max_items,a.episode_id,a.queue_file,a.attempts,a.reprocess))
