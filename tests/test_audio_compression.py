"""Real local FFmpeg checks; generated signals contain no podcast media."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import audio_compression as c
import local_worker as w


def signal(path, distinct=False):
    rate=48000;t=np.arange(rate*3)/rate
    left=np.sin(2*np.pi*440*t)*12000
    right=np.sin(2*np.pi*733*t)*12000 if distinct else left
    with wave.open(str(path),'wb') as stream:
        stream.setnchannels(2);stream.setsampwidth(2);stream.setframerate(rate)
        stream.writeframes(np.stack([left,right],axis=1).astype('<i2').tobytes())


class CompressionTests(unittest.TestCase):
    def test_full_decode_backup_and_receipt_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'audio.m4a';signal(source)
            target,info=c.ensure_compressed_audio(source,root,c.inspect_audio(source))
            self.assertEqual((info['bit_rate'],info['sample_rate'],info['channels']),(48000,24000,1))
            self.assertLess(abs(info['compression']['duration_difference_seconds']),.25)
            self.assertTrue(source.exists())
            self.assertEqual(c._sha(Path(info['compression']['original_backup'])),c._sha(source))
            original_hash=c._sha(target)
            # Crash after writing receipt, before promoting staged MP3.
            target.rename(target.with_suffix('.mp3.part'))
            with patch.object(c.subprocess,'run',side_effect=AssertionError('must reuse validated bytes')):
                restored,_=c.ensure_compressed_audio(source,root,c.inspect_audio(source))
            self.assertEqual(c._sha(restored),original_hash)
            c.cleanup_original(target,info,root)
            self.assertFalse(source.exists())
            with patch.object(c.subprocess,'run',side_effect=AssertionError('must not recompress')):
                self.assertEqual(c.ensure_compressed_audio(target,root,info,info)[0],target)

    def test_distinct_channels_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'audio.wav';signal(source,True)
            _,info=c.ensure_compressed_audio(source,root,c.inspect_audio(source))
            self.assertEqual(info['channels'],2)
            self.assertEqual(info['compression']['channel_policy'],'stereo_preserved_for_review')

    def test_encoder_failure_keeps_original_and_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'audio.wav';signal(source)
            original=c._sha(source)
            with patch.object(c.subprocess,'run',side_effect=RuntimeError('injected encoder failure')):
                with self.assertRaisesRegex(RuntimeError,'injected'):
                    c.ensure_compressed_audio(source,root,c.inspect_audio(source))
            self.assertEqual(c._sha(source),original)
            self.assertFalse((root/'audio.mp3').exists())
            target,_=c.ensure_compressed_audio(source,root,c.inspect_audio(source))
            self.assertTrue(target.exists())

    def test_worker_compression_retry_reuses_transcript_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture=root/'fixture.wav';signal(fixture)
            queue=root/'queue.json';row={'key':'fixture:compression','feed_name':'fixture','title':'fixture','audio_url':'https://fixture','url':'https://fixture'}
            w.atomic_json(queue,{'pending':[row]})
            calls=[]
            class Model:
                def __init__(self,*args,**kwargs):pass
                def transcribe(self,*args,**kwargs):
                    calls.append('asr')
                    return iter([SimpleNamespace(start=0,end=3,text='Compression retry fixture.',avg_logprob=0,no_speech_prob=0)]),None
            compressions=[]
            def compress(*args,**kwargs):
                compressions.append(1)
                if len(compressions)==1:raise RuntimeError('injected compression interruption')
                return c.ensure_compressed_audio(*args,**kwargs)
            with patch.object(w,'download',side_effect=lambda url,p:shutil.copy2(fixture,p)),patch('faster_whisper.WhisperModel',Model),patch.object(w,'ensure_compressed_audio',side_effect=compress),patch.object(w.time,'sleep'),patch.object(w,'draw_pdf',side_effect=lambda p,*args:p.write_bytes(b'pdf fixture')):
                self.assertEqual(w.run(root,'small',1,queue_file=str(queue),attempts=2),0)
            self.assertEqual(calls,['asr'])
            record=w.read_json(root/'completed.json',{})[row['key']]
            self.assertTrue(w.completed_valid(record))
            dest=Path(record['path']);self.assertFalse((dest/'audio.m4a').exists())
            with patch.object(w,'download',side_effect=AssertionError('must skip')),patch.object(w,'decode_audio',side_effect=AssertionError('must skip')),patch.object(w,'ensure_compressed_audio',side_effect=AssertionError('must skip')):
                self.assertEqual(w.run(root,'small',1,queue_file=str(queue)),0)
            self.assertEqual(w.read_json(root/'completed.json',{})[row['key']]['hashes'],record['hashes'])
            # Upgrade an older completed archive without ASR or text/PDF changes.
            metadata=w.read_json(dest/'metadata.json',{})
            original=Path(metadata['audio']['compression']['original_backup'])
            shutil.copy2(original,dest/'audio.m4a')
            (dest/'audio.mp3').unlink();(dest/'audio.compression.json').unlink()
            metadata['audio']=c.inspect_audio(dest/'audio.m4a');metadata['outputs']['audio']=str(dest/'audio.m4a')
            w.atomic_json(dest/'metadata.json',metadata)
            legacy=w.completion_record(dest,row['title'],dest/'audio.m4a',metadata['audio'])
            w.atomic_json(root/'completed.json',{row['key']:legacy})
            before={name:w.sha256_file(dest/name) for name in ('transcript.raw.json','transcript.txt','transcript.pdf','summary.md')}
            with patch('faster_whisper.WhisperModel',side_effect=AssertionError('no ASR')),patch.object(w,'download',side_effect=AssertionError('no download')):
                self.assertEqual(w.run(root,'small',1,queue_file=str(queue)),0)
            self.assertEqual(before,{name:w.sha256_file(dest/name) for name in before})
            self.assertTrue(w.completed_valid(w.read_json(root/'completed.json',{})[row['key']]))

if __name__=='__main__':unittest.main(verbosity=2)
