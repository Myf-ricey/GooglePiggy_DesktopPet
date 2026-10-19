"""Native isolated regression for manual edge hiding; accepts a built app path."""
import json, os, pathlib, subprocess, sys, tempfile, time
app=pathlib.Path(sys.argv[1]).resolve(); exe=app/'Contents/MacOS/GooglePiggy'
reports=[]
for edge in ['left','right','top','bottom']:
 state=pathlib.Path(tempfile.mkdtemp(prefix='pig-hidden-task-test-'))
 (state/'family-events').mkdir(); (state/'selected-family.json').write_text(json.dumps({'id':'hidden-parent'}))
 def send(event,status,actor='hidden-parent',agent='',turn='t1'):
  now=time.time(); payload=dict(event=event,status=status,session_id=actor,agent_id=agent,turn_id=turn,received_at=now,token=str(time.time_ns()))
  (state/'family-events'/f'{now:.6f}.json').write_text(json.dumps(payload))
 def read():
  try:return json.loads((state/'pig-heartbeat.json').read_text())
  except (OSError,ValueError):return {}
 def wait(pred,timeout=10):
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   h=read()
   if pred(h):return h
   time.sleep(.05)
  raise AssertionError((edge,read()))
 def hidden(label):
  end=time.monotonic()+.7
  while time.monotonic()<end:
   h=read(); assert h.get('presentation')=='hidden',(label,h)
   time.sleep(.05)
  reports.append(dict(edge=edge,check=label,passed=True))
 send('UserPromptSubmit','thinking')
 p=subprocess.Popen([str(exe),'--preview-edge-hide',edge],env=dict(os.environ,GOOGLEPIGGY_STATE_DIR=str(state)),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  wait(lambda h:h.get('presentation')=='hidden')
  send('PostToolUse','working'); hidden('reading_to_carrot')
  send('SubagentStart','working',agent='hidden-child');hidden('child_start')
  send('UserPromptSubmit','thinking',actor='other-parent');hidden('other_task_start')
  send('Stop','success',actor='other-parent');hidden('other_task_completion')
  send('PreCompact','compacting');hidden('compaction')
  send('PostCompact','working');hidden('compaction_finished')
  send('Interrupt','interrupted');hidden('interrupted')
  send('ResumeDetected','working');hidden('resumed')
  send('UserPromptSubmit','thinking',actor='still-running');hidden('another_task_running')
  send('Stop','success');hidden('parent_done_child_running')
  send('SubagentStop','success',agent='hidden-child')
  h=wait(lambda h:h.get('presentation')=='visible' and h.get('current_key')=='jump')
  assert h['selected_family']=='hidden-parent' and not h['tail_visible'],h
  reports.append(dict(edge=edge,check='corresponding_completion_reveals_and_celebrates',passed=True))
  time.sleep(.6);h=read();assert h['current_key']=='jump' and h['selected_family']=='hidden-parent',h
  wait(lambda h:h.get('selected_family')=='still-running')
  reports.append(dict(edge=edge,check='auto_selection_resumes_after_celebration',passed=True))
 finally:p.terminate();p.wait(timeout=5)
print(json.dumps(reports,indent=2))
app.parent.joinpath('hidden-task-regression-results.json').write_text(json.dumps(reports,indent=2))
