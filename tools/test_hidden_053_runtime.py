"""Native four-edge task-bound hiding acceptance; isolated status and process."""
import json, time
from pathlib import Path
import tools.test_windows_runtime as rt
from codex_bridge import atomic_json
from windows_pet import APP_VERSION
import subprocess, sys, uuid

def main():
    rt.STATE=rt.ROOT/'qa/hidden-053'/uuid.uuid4().hex
    rt.STATE.mkdir(parents=True)
    argv=[str(rt.TEST_EXE)] if '--exe' in sys.argv else [sys.executable,str(rt.ROOT/'pig_pet.py')]
    process=subprocess.Popen(argv+['--status-file',str(rt.STATE/'codex-status.json'),'--no-codex-observer','--qa-window'],cwd=rt.ROOT)
    passed=[]
    def hidden(root):
        time.sleep(.45)
        return rt.wait_for(lambda h:h['presentation']=='hidden' and h['selected_family']==root)
    try:
        rt.wait_for(lambda h:h.get('version')==APP_VERSION and h.get('window_visible'))
        for edge in ('left','right','top','bottom'):
            root='root-'+edge; other='other-'+edge
            rt.event(root,'UserPromptSubmit')
            rt.wait_for(lambda h:h['selected_family']==root)
            rt.command('edge',edge=edge)
            rt.wait_for(lambda h:h['presentation']=='hidden' and h['hidden_edge']==edge)
            rt.event(root,'PreToolUse'); hidden(root)
            rt.event(root,'SubagentStart',agent='child-'+edge); hidden(root)
            rt.event(other,'UserPromptSubmit'); hidden(root)
            rt.event(other,'Stop'); hidden(root)
            rt.event(root,'PreCompact'); hidden(root)
            rt.event(root,'PostCompact'); hidden(root)
            rt.event(root,'PreToolUse'); hidden(root)
            rt.event(root,'Interrupt'); hidden(root)
            rt.event(root,'ResumeDetected'); hidden(root)
            rt.command('update-preview'); hidden(root)
            rt.command('update-dismiss')
            rt.event(root,'Stop'); hidden(root)
            time.sleep(3) # parent celebration would have elapsed while child works
            rt.event('background-'+edge,'UserPromptSubmit'); hidden(root)
            rt.event(root,'SubagentStop',agent='child-'+edge)
            h=rt.wait_for(lambda h:h['presentation']=='visible' and h['current_key']=='jump' and h['selected_family']==root)
            time.sleep(1.5)
            rt.wait_for(lambda h:h['current_key']=='jump' and h['selected_family']==root)
            rt.wait_for(lambda h:h['selected_family']=='background-'+edge and h['current_key']=='reading')
            rt.event('background-'+edge,'SessionEnd')
            passed.append(edge+': tool, child, other family, compaction, interrupt, update stay hidden; full celebration then resume other work')
        rt.event('tail','UserPromptSubmit')
        rt.wait_for(lambda h:h['selected_family']=='tail')
        rt.command('edge',edge='right'); rt.wait_for(lambda h:h['presentation']=='hidden')
        rt.command('reveal'); rt.wait_for(lambda h:h['presentation']=='visible')
        passed.append('Tail reveal handler releases running-family hide')
        rt.command('exit'); assert process.wait(timeout=5)==0
        atomic_json(rt.ROOT/'qa/hidden-053-report.json',dict(passed=True,pass_items=passed,state_dir=str(rt.STATE)))
        print(json.dumps(dict(passed=True,pass_items=passed),indent=2))
    finally:
        if process.poll() is None: process.terminate(); process.wait(timeout=5)

if __name__=='__main__': main()
