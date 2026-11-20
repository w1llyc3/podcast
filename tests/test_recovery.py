"""Offline fault injection: actual HTTP interruption, retries and checkpoint restart."""
import sys
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
spec=importlib.util.spec_from_file_location('worker',Path(__file__).resolve().parents[1]/'scripts/local_worker.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

class RecoveryTests(unittest.TestCase):
    def test_exclusive_worker_lock(self):
        from filelock import Timeout
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            with w.FileLock(str(out/'.worker.lock')):
                with self.assertRaises(Timeout):w.run(out,'small',1,queue_file=str(out/'absent.json'))

    def test_http_disconnect_range_resume(self):
        payload=bytes(range(256))*8192
        ranges=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                start=int(self.headers.get('Range','bytes=0-').split('=')[1].split('-')[0])
                ranges.append(start)
                self.send_response(206 if start else 200)
                self.send_header('ETag','"fixed"')
                self.send_header('Content-Length',str(len(payload)-start))
                if start:self.send_header('Content-Range',f'bytes {start}-{len(payload)-1}/{len(payload)}')
                self.end_headers()
                if len(ranges)==1:
                    self.wfile.write(payload[:700000]);self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR);self.connection.close()
                else:self.wfile.write(payload[start:])
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                out=Path(directory)/'audio.m4a'
                w.download(f'http://127.0.0.1:{server.server_port}/audio',out)
                self.assertEqual(out.read_bytes(),payload)
                self.assertGreater(ranges[1],0)
                self.assertFalse(out.with_suffix('.m4a.part').exists())
        finally:server.shutdown();server.server_close();thread.join()

    def test_transcript_restart_preserves_committed_chunk(self):
        calls=[]
        class Model:
            def transcribe(self,audio,**kwargs):
                calls.append(len(audio))
                if len(calls)==2: raise RuntimeError('Injected interruption')
                return iter([SimpleNamespace(start=0,end=len(audio)/16000,text='中文断点测试',avg_logprob=-.2,no_speech_prob=.01)]),None
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'raw.json';audio=np.zeros(16000*181,dtype=np.float32)
            with self.assertRaisesRegex(RuntimeError,'Injected'):
                w.transcribe_chunks(audio,Model(),p,{'sha':'fixed'})
            before=json.loads(p.read_text(encoding='utf-8'))
            self.assertEqual(len(before['chunks']),1)
            after=w.transcribe_chunks(audio,Model(),p,{'sha':'fixed'})
            self.assertEqual(after['segments'][0],before['segments'][0])
            self.assertEqual([c['start'] for c in after['chunks']],[0,90,180])
            self.assertEqual(len(calls),4)
            self.assertTrue(after['complete'])

    def test_episode_failure_then_retry_and_dedup(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);queue=out/'queue.json'
            row={'key':'fixture:1','feed_name':'测试','title':'测试','audio_url':'http://fixture/audio','url':'http://fixture/1'}
            w.atomic_json(queue,{'pending':[row,row]})
            def broken(*args):raise RuntimeError('Injected network failure')
            with patch.object(w,'download',side_effect=broken):
                self.assertEqual(w.consume(out,'small',3,None,str(queue),1),1)
            self.assertEqual(w.read_json(out/'worker-state.json',{})[row['key']]['status'],'failed')
            class Model:
                def __init__(self,*args,**kwargs):pass
                def transcribe(self,*args,**kwargs):
                    return iter([SimpleNamespace(start=0,end=1,text='真实故障路径测试',avg_logprob=-.1,no_speech_prob=0)]),None
            def download(url,p):p.write_bytes(b'fixture')
            def compress(source,root,probe,prior=None):
                target=source.with_name('audio.mp3');target.write_bytes(b'compressed-fixture')
                return target,{**probe,'sha256':w.sha256_file(target),'compression':{'source_sha256':'fixed','validated_full_decode':True,'settings':{'bit_rate':48000,'sample_rate':24000,'channels':1}}}
            with patch.object(w,'download',side_effect=download),patch.object(w,'decode_audio',return_value=(np.zeros(16000),{'sha256':'fixed','duration_seconds':1})),patch('faster_whisper.WhisperModel',Model),patch.object(w,'ensure_compressed_audio',side_effect=compress):
                self.assertEqual(w.consume(out,'small',3,None,str(queue),1),0)
            with patch.object(w,'download',side_effect=AssertionError('must skip')),patch.object(w,'decode_audio',side_effect=AssertionError('must skip')):
                self.assertEqual(w.consume(out,'small',3,None,str(queue),1),0)
            self.assertEqual(len(w.read_json(out/'completed.json',{})),1)
            self.assertEqual(w.read_json(out/'worker-state.json',{})[row['key']]['attempts'],2)
            # A completed item at the head must not starve the next queued episode.
            w.atomic_json(queue,{'pending':[row,{**row,'key':'fixture:2'}]})
            with patch.object(w,'download',side_effect=download),patch.object(w,'decode_audio',return_value=(np.zeros(16000),{'sha256':'fixed','duration_seconds':1})),patch('faster_whisper.WhisperModel',Model),patch.object(w,'ensure_compressed_audio',side_effect=compress):
                self.assertEqual(w.consume(out,'small',1,None,str(queue),1),0)
            self.assertEqual(len(w.read_json(out/'completed.json',{})),2)

if __name__=='__main__':unittest.main(verbosity=2)
