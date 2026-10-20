"""Verify actual local outputs, render every page, optionally test real-model recovery."""
import argparse
import json
from pathlib import Path
import re
import hashlib
import fitz
from pypdf import PdfReader
import local_worker as w

def verify(root,resume=False):
    evidence=root/'evidence';evidence.mkdir(exist_ok=True)
    records=w.read_json(root/'completed.json',{})
    results=[]
    for row in records.values():
        dest=Path(row['path'])
        raw=w.read_json(dest/'transcript.raw.json',{})
        metadata=w.read_json(dest/'metadata.json',{})
        txt=(dest/'transcript.txt').read_text(encoding='utf-8')
        normalize=lambda s:re.sub(r'\s+','',s)
        reader=PdfReader(dest/'transcript.pdf')
        page_text=[normalize(p.extract_text()) for p in reader.pages]
        # A long ASR segment may cross a page; remove the known running footer
        # before joining pages so it cannot appear inside the copied segment.
        page_text=[re.sub(r'完整文字稿·无时间线第\d+页$','',p) for p in page_text]
        first=normalize(metadata['title'])+normalize(metadata.get('url',''))
        assert page_text[0].startswith(first)
        page_text[0]=page_text[0][len(first):]
        extracted=''.join(page_text)
        assert normalize(txt)==normalize(''.join(s['text'] for s in raw['segments']))
        assert all(normalize(s['text']) in normalize(extracted) for s in raw['segments'])
        assert normalize(txt)==extracted
        assert not re.search(r'\[\d+:\d+',txt)
        assert all(len(p.extract_text().strip())>50 for p in reader.pages)
        assert raw['complete'] and raw['chunks'][0]['start']==0
        assert abs(raw['chunks'][-1]['end']-metadata['audio']['duration_seconds'])<.01
        assert all(abs(a['end']-b['start'])<.01 for a,b in zip(raw['chunks'],raw['chunks'][1:]))
        doc=fitz.open(dest/'transcript.pdf')
        for i,p in enumerate(doc):p.get_pixmap(matrix=fitz.Matrix(1.25,1.25)).save(str(evidence/f'page-{i+1}.png'))
        # Check every used character exists in the embedded Chinese font.
        from fontTools.ttLib import TTFont
        font=TTFont(r'C:\Windows\Fonts\simhei.ttf')
        cmap=font.getBestCmap()
        missing=sorted({c for c in metadata['title']+txt if not c.isspace() and ord(c) not in cmap})
        assert not missing,missing
        result={'path':str(dest),'pages':len(reader.pages),'segments':len(raw['segments']),'paragraphs':len(w.reading_paragraphs(raw['segments'])),'txt_characters':len(txt),'all_segments_extractable':True,'raw_txt_exact_match':True,'no_timestamp_tokens':True,'no_empty_pages':True,'missing_font_glyphs':missing,'page_characters':[len(p.extract_text()) for p in reader.pages],'audio':metadata['audio'],'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.name in ('audio.m4a','transcript.raw.json','transcript.txt','transcript.pdf','metadata.json','summary.md')}}
        w.atomic_json(evidence/'episode-queue.json',{'pending':[metadata]})
        if resume:
            audio,_=w.decode_audio(dest/'audio.m4a')
            checkpoint=json.loads(json.dumps(raw))
            last=checkpoint['chunks'].pop()
            checkpoint['segments']=[s for s in checkpoint['segments'] if s['start']<last['start']]
            checkpoint.pop('complete',None)
            recovery=evidence/'real-resume.raw.json';w.atomic_json(recovery,checkpoint)
            from faster_whisper import WhisperModel
            model=WhisperModel(metadata['transcription']['model'],device='cpu',compute_type='int8',download_root=str(root/'models'),local_files_only=True,cpu_threads=8)
            class CountingModel:
                calls=0
                def transcribe(self,*args,**kwargs):
                    self.calls+=1
                    return model.transcribe(*args,**kwargs)
            counter=CountingModel()
            after=w.transcribe_chunks(audio,counter,recovery,raw['fingerprint'])
            assert counter.calls==1
            assert after['segments'][:len(checkpoint['segments'])]==checkpoint['segments']
            assert len(after['chunks'])==len(raw['chunks']) and after['complete']
            result['real_model_recovery']={'kept_chunks':len(checkpoint['chunks']),'transcribed_chunks':counter.calls,'prefix_exact_match':True,'completed':True}
        results.append(result)
    w.atomic_json(evidence/'pdf-check.json',results)
    print(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',default=r'D:\podcast');ap.add_argument('--resume-test',action='store_true')
    a=ap.parse_args();verify(Path(a.output),a.resume_test)
