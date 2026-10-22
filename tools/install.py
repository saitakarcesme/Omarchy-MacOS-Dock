#!/usr/bin/env python3
"""User-local, reversible installer. Run from a clone; never writes system files."""
import argparse, copy, datetime, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RECIPE=json.loads((ROOT/'recipe.json').read_text())
NAME=RECIPE['name'];SLUG=RECIPE['slug']
HOME=Path(os.environ.get('OMARCHY_INSTALL_HOME',str(Path.home()))).resolve()
STATE=HOME/'.local/state'/SLUG
TEST=bool(os.environ.get('OMARCHY_INSTALL_HOME'))
CONFIG=HOME/'.config/omarchy/shell.json'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def read_config():return json.loads(CONFIG.read_text()) if CONFIG.exists() else {'version':1}
def block(path,body,remove=False):
    start=f'-- BEGIN {NAME}';end=f'-- END {NAME}'
    old=path.read_text() if path.exists() else ''
    if not remove and start not in old and body.strip() in old:return old
    clean=re.sub(r'\n?'+re.escape(start)+r'\n.*?\n'+re.escape(end)+r'\n?', '\n',old,flags=re.S).rstrip()
    return clean+('\n' if remove else '\n\n'+start+'\n'+body.rstrip()+'\n'+end+'\n')
def check():
    if TEST:return
    missing=[x for x in RECIPE['dependencies'] if not shutil.which(x)]
    if missing:raise SystemExit('Missing dependencies: '+', '.join(missing))
    if not (HOME/'.config/hypr/hyprland.lua').exists():raise SystemExit('Requires Omarchy with Hyprland Lua configuration (0.55+).')
    if not Path('/usr/share/omarchy/shell/Ui/Panel.qml').exists():raise SystemExit('Requires the Omarchy Quickshell desktop.')
def plugin_meta():
    result={}
    for p in (HOME/'.config/omarchy/plugins').glob('*/manifest.json'):
        try:
            m=json.loads(p.read_text());result[m['id']]=m
        except (ValueError,KeyError):pass
    return result
def install_config(config):
    kind=RECIPE['kind'];meta=plugin_meta();bar=config.setdefault('bar',{})
    if kind=='light':
        clones={i for i,m in meta.items() if m.get('omarchy',{}).get('clonedFrom')=='omarchy.menu'}
        sources=clones|{'omarchy.menu'};sources.discard('omarchylight.menu')
        layout=bar.setdefault('layout',{})
        for section,entries in layout.items():
            if isinstance(entries,list):
                for e in entries:
                    if isinstance(e,dict) and e.get('id') in sources:e['id']='omarchylight.menu'
        plugins=config.setdefault('plugins',[])
        if not any(e.get('id')=='omarchylight.menu' for e in plugins):plugins.append({'id':'omarchylight.menu'})
        disabled=set(config.get('disabledPlugins',[]));disabled.update(sources);disabled.discard('omarchylight.menu');config['disabledPlugins']=sorted(disabled)
    elif kind=='bar':
        layout=bar.get('layout',{});oldright=layout.get('right',[])
        menu=next((e.get('id') for e in layout.get('left',[]) if e.get('id')=='omarchy.menu' or meta.get(e.get('id'),{}).get('omarchy',{}).get('clonedFrom')=='omarchy.menu'),'omarchy.menu')
        right=[]
        removed={'omarchy.indicators','omarchy.weather'}
        for e in oldright:
            i=e.get('id','')
            if i in removed:continue
            if i=='omarchy.tray' or meta.get(i,{}).get('omarchy',{}).get('clonedFrom')=='omarchy.tray':e=dict(e,id='macos.tray')
            if not any(x.get('id')==e.get('id') for x in right):right.append(e)
        if not right:right=[{'id':i} for i in RECIPE['defaultRight']]
        if not any(e.get('id')=='macos.tray' for e in right):right.insert(0,{'id':'macos.tray'})
        bar.update({'id':'macos.bar','position':'top','centerAnchor':'omarchy.workspaces','layout':{
            'left':[{'id':menu},{'id':'omarchy.spacer','size':10},{'id':'macos.active-app'}],
            'center':[{'id':'omarchy.workspaces'}],'right':right}})
        plugins=config.setdefault('plugins',[])
        for e in plugins:
            if 'bar' in meta.get(e.get('id'),{}).get('kinds',[]):e['id']='macos.bar'
        if not any(e.get('id')=='macos.bar' for e in plugins):plugins.append({'id':'macos.bar'})
        config['plugins']=list({e['id']:e for e in plugins}.values())
    return config

def reload():
    if TEST:return
    subprocess.run(['hyprctl','reload'],check=True,stdout=subprocess.DEVNULL)
    errors=subprocess.check_output(['hyprctl','configerrors'],text=True).strip()
    if errors:raise RuntimeError('Hyprland reported configuration errors: '+errors)
    if RECIPE['kind']!='dock':subprocess.run(['omarchy','restart','shell'],check=True)
    else:
        subprocess.run(['quickshell','kill','-p',str(HOME/'.config/quickshell/classic-dock')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        import time
        dock_path=str(HOME/'.config/quickshell/classic-dock')
        # Quickshell kill returns before the old instance releases its lock.
        for _ in range(50):
            status=subprocess.run(['quickshell','ipc','-p',dock_path,'call','dock','status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if status.returncode!=0:break
            time.sleep(.1)
        time.sleep(.2)
        subprocess.run(['quickshell','-d','-n','-p',dock_path],check=True)
        for _ in range(50):
            time.sleep(.1)
            if subprocess.run(['quickshell','ipc','-p',dock_path,'call','dock','status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:return
        raise RuntimeError('Dock did not answer its health check.')

def install(args):
    check();writes={};config_before=read_config()
    for spec in RECIPE['copies']:
        source=ROOT/spec['source'];dest=HOME/spec['destination']
        paths=[source] if source.is_file() else [p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        for p in paths:
            target=dest if source.is_file() else dest/p.relative_to(source)
            if target.name=='settings.json' and target.exists():continue
            writes[target]=p.read_bytes()
    for path,body in RECIPE.get('lua',{}).items():writes[HOME/path]=block(HOME/path,body).encode()
    if RECIPE['kind']!='dock':writes[CONFIG]=(json.dumps(install_config(copy.deepcopy(config_before)),indent=2)+'\n').encode()
    if args.dry_run:
        print('Would install '+NAME+' into '+str(HOME))
        for p in writes:print(p.relative_to(HOME))
        return
    previous=None
    marker=STATE/'latest'
    if marker.exists():
        previous=Path(marker.read_text().strip())
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');backup=STATE/'backups'/stamp;backup.mkdir(parents=True)
    records=[]
    try:
        for target,data in writes.items():
            relative=str(target.relative_to(HOME));old=backup/'files'/relative
            existed=target.exists()
            if existed:old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,old)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            records.append({'path':relative,'existed':existed,'sha256':digest(target)})
        manifest={'name':NAME,'files':records,'configBefore':config_before,'configAfter':read_config()}
        (backup/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if not args.no_reload:reload()
        # Updates keep the original pre-install baseline for a complete uninstall.
        if previous and (previous/'manifest.json').exists():
            baseline=json.loads((previous/'manifest.json').read_text())
            baseline_records={r['path']:r for r in baseline['files']}
            for r in records:
                if r['path'] in baseline_records:
                    original=baseline_records[r['path']]
                    r['existed']=original['existed']
                    if original['existed']:
                        dst=backup/'baseline'/r['path'];dst.parent.mkdir(parents=True,exist_ok=True)
                        src=previous/('baseline' if baseline.get('baseline') else 'files')/r['path']
                        shutil.copy2(src,dst)
                elif r['existed']:
                    dst=backup/'baseline'/r['path'];dst.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(backup/'files'/r['path'],dst)
            manifest['configBefore']=baseline['configBefore']
            manifest['baseline']=True
            (backup/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        (STATE/'latest').write_text(str(backup))
    except Exception:
        for record in reversed(records):
            target=HOME/record['path'];old=backup/'files'/record['path']
            if record['existed']:shutil.copy2(old,target)
            else:target.unlink(missing_ok=True)
        raise
    print('Installed '+NAME+'; backup: '+str(backup))

def uninstall(args):
    marker=STATE/'latest'
    if not marker.exists():raise SystemExit('No installation backup found.')
    backup=Path(marker.read_text().strip());manifest=json.loads((backup/'manifest.json').read_text())
    config=read_config();before=manifest['configBefore'];after=manifest['configAfter']
    for rec in reversed(manifest['files']):
        target=HOME/rec['path'];old=backup/('baseline' if manifest.get('baseline') else 'files')/rec['path']
        if rec['path'] in RECIPE.get('lua',{}):
            if rec['existed'] and digest(target)==rec['sha256']:
                shutil.copy2(old,target)
            else:target.write_text(block(target,'',True))
            continue
        if target==CONFIG:
            if config.get('bar')==after.get('bar'):config['bar']=before.get('bar',{})
            else:
                # A subsequently installed companion may have edited the bar.
                swaps={'macos.bar':before.get('bar',{}).get('id','omarchy.bar'),'macos.tray':'omarchy.tray','macos.active-app':'omarchy.active-window'} if RECIPE['kind']=='bar' else {'omarchylight.menu':'omarchy.menu'}
                if config.get('bar',{}).get('id') in swaps:config['bar']['id']=swaps[config['bar']['id']]
                for entries in config.get('bar',{}).get('layout',{}).values():
                    for e in entries:
                        if e.get('id') in swaps:e['id']=swaps[e['id']]
            for key in ['plugins','disabledPlugins']:
                old_entries=before.get(key,[]);installed=after.get(key,[])
                added=[e for e in installed if e not in old_entries]
                current=[e for e in config.get(key,[]) if e not in added]
                removed=[e for e in old_entries if e not in installed]
                config[key]=current+[e for e in removed if e not in current]
            CONFIG.write_text(json.dumps(config,indent=2)+'\n');continue
        if digest(target)!=rec['sha256'] and not args.force:
            print('Preserving modified file: '+str(target));continue
        if rec['existed']:shutil.copy2(old,target)
        else:target.unlink(missing_ok=True)
    if not args.no_reload:
        if RECIPE['kind']=='dock' and not TEST:
            subprocess.run(['quickshell','kill','-p',str(HOME/'.config/quickshell/classic-dock')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(['hyprctl','reload'],check=True,stdout=subprocess.DEVNULL)
        else:reload()
    marker.unlink(missing_ok=True)
    print('Uninstalled '+NAME+'; backup retained at '+str(backup))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['install','uninstall']);ap.add_argument('--dry-run',action='store_true');ap.add_argument('--no-reload',action='store_true');ap.add_argument('--force',action='store_true');args=ap.parse_args()
    if args.action=='uninstall' and args.dry_run:raise SystemExit('Use install --dry-run to preview installation.')
    (install if args.action=='install' else uninstall)(args)
if __name__=='__main__':main()
