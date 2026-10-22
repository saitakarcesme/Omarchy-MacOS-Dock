#!/usr/bin/env python3
"""Exercise install/update/uninstall using a temporary home; no live changes."""
import json, os, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class InstallerTest(unittest.TestCase):
 def test_round_trip_and_update(self):
  with tempfile.TemporaryDirectory() as d:
   home=Path(d);config=home/'.config/omarchy/shell.json';config.parent.mkdir(parents=True)
   original={'version':1,'bar':{'id':'omarchy.bar','layout':{'left':[{'id':'omarchy.menu'}],'center':[],'right':[{'id':'omarchy.audio'},{'id':'custom.extra'}]}},'plugins':[],'disabledPlugins':[],'unrelated':{'keep':True}}
   config.write_text(json.dumps(original));hypr=home/'.config/hypr';hypr.mkdir()
   for f in ('bindings.lua','autostart.lua','looknfeel.lua'):(hypr/f).write_text('-- my existing configuration\n')
   env=dict(os.environ,OMARCHY_INSTALL_HOME=d)
   def run(action):subprocess.run(['python3',str(ROOT/'tools/install.py'),action,'--no-reload'],env=env,check=True,stdout=subprocess.DEVNULL)
   run('install');run('install')
   self.assertEqual(json.loads(config.read_text())['unrelated'],original['unrelated'])
   recipe=json.loads((ROOT/'recipe.json').read_text())
   for relative in recipe.get('lua',{}):self.assertEqual((home/relative).read_text().count('-- BEGIN '+recipe['name']),1)
   run('uninstall');self.assertEqual(json.loads(config.read_text()),original)
   for f in hypr.iterdir():self.assertEqual(f.read_text(),'-- my existing configuration\n')
if __name__=='__main__':unittest.main()
