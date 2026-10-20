import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import os

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/rss_watch.py'

class RssTests(unittest.TestCase):
    def test_baseline_duplicate_guid_and_repeat(self):
        old=os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                Path('config').mkdir()
                Path('config/feeds.json').write_text(json.dumps([{'id':'fixture','name':'test','rss':'https://fixture','enabled':True}]))
                baseline=SimpleNamespace(entries=[{'id':'old'}])
                new=SimpleNamespace(entries=[{'id':'new','title':'new','enclosures':[{'href':'https://fixture/audio'}]},{'id':'new'},{'id':'old'}])
                with patch('feedparser.parse',return_value=baseline):runpy.run_path(str(SCRIPT))
                self.assertEqual(json.loads(Path('queue/state.json').read_text())['pending'],[])
                with patch('feedparser.parse',return_value=new):
                    runpy.run_path(str(SCRIPT));runpy.run_path(str(SCRIPT))
                state=json.loads(Path('queue/state.json').read_text())
                self.assertEqual(len(state['pending']),1)
                self.assertEqual(len(state['feeds']['fixture']),2)
                self.assertEqual(state['pending'][0]['audio_url'],'https://fixture/audio')
                os.chdir(old)
        finally:os.chdir(old)

if __name__=='__main__':unittest.main(verbosity=2)
