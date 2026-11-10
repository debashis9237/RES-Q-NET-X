import json, time
from datetime import datetime
import requests
import streamlit as st
import plotly.graph_objects as go

OLLAMA = 'http://localhost:11434'
DEFAULT_MODEL = 'gemma4:e2b'
LOW_BATTERY = 20
MIN_RELAY_BATTERY = 30
MIN_LINK = 45

st.set_page_config(page_title='RESQNET X | Autopilot Simulator', page_icon='📡', layout='wide')
st.markdown('''<style>
.stApp{background:#071321;color:#e8f0f8}[data-testid="stSidebar"]{background:#0c1c2d}
.hero{padding:1.2rem 1.5rem;border-radius:16px;background:linear-gradient(115deg,#102b48,#123d54 65%,#0d273c);border:1px solid #24516d;margin-bottom:1rem}
.hero h1{margin:0;color:#eff8ff;font-size:2rem}.hero p{margin:.35rem 0 0;color:#b9d4e7}
.node{background:#102238;border:1px solid #29475f;border-radius:14px;padding:14px;min-height:135px}
.node h3{margin:0 0 4px;color:#eef7ff;font-size:1.05rem}.muted{color:#9eb7ca;font-size:.85rem}
.metric{font-size:1.65rem;font-weight:750;margin:5px 0}.ok{color:#55d6a5}.warn{color:#ffbf69}.bad{color:#ff7777}
.pill{display:inline-block;padding:3px 9px;border-radius:99px;background:#203b53;color:#cfe8f7;font-size:.75rem}
.stButton button{border-radius:9px;font-weight:650}
</style>''', unsafe_allow_html=True)

def fresh_state():
    return {'nodes': {
        'A': {'name':'Node A','battery':22,'online':True,'link':76,'queue':2},
        'B': {'name':'Node B','battery':78,'online':True,'link':88,'queue':0},
        'C': {'name':'Node C','battery':91,'online':True,'link':100,'queue':0}},
        'active':'A','pending':None,'events':[], 'summary':'No AI operation has been run yet.',
        'tool_log':'None','mode':'Not run'}

if 'sim' not in st.session_state: st.session_state.sim=fresh_state()
sim=st.session_state.sim

def log(msg, kind='INFO'):
    sim['events'].insert(0, {'time':datetime.now().strftime('%H:%M:%S'),'type':kind,'event':msg})
    sim['events']=sim['events'][:100]

def snapshot():
    nodes={}
    for k,n in sim['nodes'].items():
        nodes[k]={**n,'role':('GATEWAY' if k=='C' else ('ACTIVE RELAY' if k==sim['active'] else 'STANDBY RELAY')),
                  'eligible_as_relay':k in ('A','B') and n['online'] and n['battery']>=MIN_RELAY_BATTERY and n['link']>=MIN_LINK}
    return {'active_relay':sim['active'],'gateway_online':sim['nodes']['C']['online'],
            'low_battery_threshold_pct':LOW_BATTERY,'minimum_relay_battery_pct':MIN_RELAY_BATTERY,
            'minimum_link_quality':MIN_LINK,'nodes':nodes}

def candidates(exclude=''):
    ids=[x for x in ('A','B') if x!=exclude and sim['nodes'][x]['online'] and sim['nodes'][x]['battery']>=MIN_RELAY_BATTERY and sim['nodes'][x]['link']>=MIN_LINK]
    return sorted(ids,key=lambda x:(sim['nodes'][x]['battery'],sim['nodes'][x]['link']),reverse=True)

def handover(source,target):
    source=str(source).upper(); target=str(target).upper()
    if source not in ('A','B') or target not in ('A','B') or source==target:
        return {'ok':False,'status':'REJECTED','reason':'Invalid source or target relay.'}
    if sim['active']!=source and sim['nodes'][source]['online']:
        return {'ok':False,'status':'REJECTED','reason':f'{source} is not the active relay.'}
    if not sim['nodes']['C']['online']:
        return {'ok':False,'status':'REJECTED','reason':'Gateway Node C is offline; end-to-end verification is impossible.'}
    n=sim['nodes'][target]
    if not n['online']: return {'ok':False,'status':'REJECTED','reason':f'{target} is offline.'}
    if n['battery']<MIN_RELAY_BATTERY: return {'ok':False,'status':'REJECTED','reason':f'{target} battery is below {MIN_RELAY_BATTERY}%.'}
    if n['link']<MIN_LINK: return {'ok':False,'status':'REJECTED','reason':f'{target} link quality is below {MIN_LINK}%.'}
    task=f'HANDOVER-{int(time.time())}'
    sim['pending']=task; log(f'{task}: requested relay handover {source} → {target}.','ACTION')
    log(f'{target} accepted task offer; verification packet sent to gateway.','ACK')
    verified=sim['nodes'][target]['online'] and sim['nodes'][target]['link']>=MIN_LINK
    if not verified:
        sim['pending']=None; log(f'{task}: verification failed; old assignment retained.','ERROR')
        return {'ok':False,'status':'VERIFY_FAILED','reason':'Forwarding verification failed.'}
    old=sim['active']; sim['active']=target; sim['pending']=None
    sim['nodes'][old]['queue']=max(0,sim['nodes'][old]['queue']-1); sim['nodes'][target]['queue']+=1
    log(f'{task}: forwarding verified. Active relay is now {target}.','SUCCESS')
    return {'ok':True,'status':'VERIFIED','task_id':task,'previous_relay':old,'new_relay':target,
            'verification':'Gateway received the simulated forwarding test packet.'}

def alternate_route():
    if not sim['nodes']['C']['online']: return {'ok':False,'status':'REJECTED','reason':'Gateway is offline.'}
    opts=candidates()
    if not opts: return {'ok':False,'status':'NO_ROUTE','reason':'No eligible relay is available.'}
    target=opts[0]
    if target==sim['active']: return {'ok':True,'status':'UNCHANGED','active_relay':target,'reason':'Current relay is the best eligible option.'}
    return handover(sim['active'],target)

def fallback():
    current=sim['active']; n=sim['nodes'][current]
    reasons=[]
    if not n['online']: reasons.append(f'{current} is offline')
    if n['battery']<LOW_BATTERY: reasons.append(f'{current} battery is {n["battery"]}%')
    if n['link']<MIN_LINK: reasons.append(f'{current} link quality is degraded')
    if not reasons:
        log('Rule-based autopilot: current relay is healthy; no change needed.')
        return {'ok':True,'status':'NO_ACTION','reason':'Current relay is healthy.'}
    opts=candidates(exclude=current)
    if not opts:
        log('No eligible alternate relay; operator attention required.','ERROR')
        return {'ok':False,'status':'NO_CANDIDATE','reason':'No eligible alternate relay is available.'}
    log('Rule-based fallback detected: '+'; '.join(reasons)+'.','WARNING')
    return handover(current,opts[0])

TOOLS=[
 {'type':'function','function':{'name':'get_network_snapshot','description':'Read current node battery, online state, roles and link quality.','parameters':{'type':'object','properties':{},'required':[]}}},
 {'type':'function','function':{'name':'request_relay_handover','description':'Request a simulated relay handover. Simulator validates candidate battery, online state, link, gateway, acceptance and forwarding verification.','parameters':{'type':'object','properties':{'source_node':{'type':'string','enum':['A','B']},'target_node':{'type':'string','enum':['A','B']}},'required':['source_node','target_node']}}},
 {'type':'function','function':{'name':'request_alternate_route','description':'Choose and verify the best eligible alternate relay route.','parameters':{'type':'object','properties':{},'required':[]}}}
]

def execute_tool(name,args):
    # Strict allow-list: never run arbitrary model-generated code or shell commands.
    if name=='get_network_snapshot': return {'ok':True,'snapshot':snapshot()}
    if name=='request_relay_handover': return handover(args.get('source_node',''),args.get('target_node',''))
    if name=='request_alternate_route': return alternate_route()
    return {'ok':False,'status':'BLOCKED','reason':'Tool is not allow-listed.'}

def ollama_status():
    try:
        r=requests.get(OLLAMA+'/api/tags',timeout=2.5); r.raise_for_status()
        return True,[m.get('name','') for m in r.json().get('models',[])]
    except requests.RequestException: return False,[]

def run_gemma(model):
    system='''You are RESQNET X Network Commander operating a VIRTUAL SIMULATOR, not physical hardware. Read the current state using get_network_snapshot before deciding. Maintain a verified path through relay A or B to gateway C. A relay must be online, have at least 30% battery and link quality >=45. If active relay is offline, below 20% battery, or link quality is below 45, select an eligible alternative. Node C is gateway, not a relay candidate. Do not claim success unless handover tool returns VERIFIED. If no safe candidate exists, explain that. Use tools to perform actions, not just describe them.'''
    messages=[{'role':'system','content':system},{'role':'user','content':'Inspect the current network and take the necessary permitted action. Current state: '+json.dumps(snapshot())}]
    executed=[]; final_text=''
    for _ in range(3):
        payload={'model':model,'messages':messages,'tools':TOOLS,'stream':False,'options':{'temperature':0.1},'keep_alive':'5m'}
        try:
            r=requests.post(OLLAMA+'/api/chat',json=payload,timeout=180); r.raise_for_status(); body=r.json()
        except requests.RequestException as e: return {'ok':False,'error':f'Could not call Ollama at {OLLAMA}: {e}'}
        assistant=body.get('message',{}); calls=assistant.get('tool_calls') or []; final_text=assistant.get('content','') or final_text
        if not calls: break
        messages.append({'role':'assistant','content':assistant.get('content',''),'tool_calls':calls})
        for call in calls:
            fn=call.get('function',{}); name=fn.get('name',''); args=fn.get('arguments',{})
            if not isinstance(args,dict): args={}
            result=execute_tool(name,args); executed.append({'tool':name,'arguments':args,'result':result})
            messages.append({'role':'tool','tool_name':name,'content':json.dumps(result)})
    log(f'Gemma 4 requested {len(executed)} tool operation(s).','AI') if executed else log('Gemma 4 responded without an operational tool request.')
    return {'ok':True,'summary':final_text or 'Gemma interaction completed.','executed':executed}

def graph():
    pos={'A':(0.12,0.5),'B':(0.5,0.88),'C':(0.88,0.5)}; traces=[]
    for u,v in [('A','C'),('B','C'),('A','B')]:
        x1,y1=pos[u]; x2,y2=pos[v]; alive=sim['nodes'][u]['online'] and sim['nodes'][v]['online']
        active=(u==sim['active'] and v=='C')
        traces.append(go.Scatter(x=[x1,x2],y=[y1,y2],mode='lines',line={'color':'#4ad6a1' if active and alive else ('#399dc9' if alive else '#ef6262'),'width':5 if active else 2,'dash':'solid' if alive else 'dash'},hoverinfo='skip',showlegend=False))
    xs=[]; ys=[]; texts=[]; colours=[]; hovers=[]
    for k,(x,y) in pos.items():
        n=sim['nodes'][k]; xs.append(x); ys.append(y); texts.append(f'{k}<br>{n["battery"]}%')
        colours.append('#596b7d' if not n['online'] else ('#ef6262' if n['battery']<LOW_BATTERY else ('#f2ae4a' if n['battery']<MIN_RELAY_BATTERY else '#20a889')))
        hovers.append(f'{n["name"]}<br>Battery: {n["battery"]}%<br>Online: {n["online"]}<br>Link: {n["link"]}%')
    traces.append(go.Scatter(x=xs,y=ys,mode='markers+text',text=texts,textposition='bottom center',marker={'size':42,'color':colours,'line':{'color':'#d8e8f5','width':2}},hovertext=hovers,hoverinfo='text',showlegend=False))
    fig=go.Figure(traces); fig.update_layout(height=330,margin={'l':5,'r':5,'t':10,'b':5},paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',xaxis={'visible':False,'range':[0,1]},yaxis={'visible':False,'range':[0.2,1.05]})
    return fig

def card(k):
    n=sim['nodes'][k]; active=k==sim['active']; role='GATEWAY' if k=='C' else ('ACTIVE RELAY' if active else 'STANDBY RELAY')
    cls='bad' if n['battery']<LOW_BATTERY else ('warn' if n['battery']<MIN_RELAY_BATTERY else 'ok')
    status='ONLINE' if n['online'] else 'OFFLINE'
    st.markdown(f'<div class="node"><h3>{n["name"]}</h3><span class="pill">{status}</span> <span class="pill">{role}</span><div class="metric {cls}">{n["battery"]}%</div><div class="muted">Battery · Link {n["link"]}% · Queue {n["queue"]}</div></div>',unsafe_allow_html=True)

with st.sidebar:
    st.markdown('## 📡 RESQNET X'); st.caption('Virtual network and AI operations')
    st.markdown('### Simulation controls')
    if st.button('⚡ Drain active relay to 8%',use_container_width=True):
        a=sim['active']; sim['nodes'][a]['battery']=8; log(f'Operator forced {a} battery to 8%.','WARNING'); st.rerun()
    if st.button('🔌 Disconnect active relay',use_container_width=True):
        a=sim['active']; sim['nodes'][a]['online']=False; log(f'Operator disconnected {a}.','WARNING'); st.rerun()
    chosen=st.selectbox('Choose node to modify',['A','B','C'])
    val=st.slider('Set battery',0,100,int(sim['nodes'][chosen]['battery']))
    if st.button('Apply battery level',use_container_width=True):
        sim['nodes'][chosen]['battery']=val; log(f'Node {chosen} battery set to {val}%.'); st.rerun()
    if st.button('Disconnect selected node',use_container_width=True):
        sim['nodes'][chosen]['online']=False; log(f'Node {chosen} disconnected.','WARNING'); st.rerun()
    if st.button('Reconnect all nodes',use_container_width=True):
        for n in sim['nodes'].values(): n['online']=True
        log('All nodes reconnected.'); st.rerun()
    if st.button('Reset simulation',use_container_width=True): st.session_state.sim=fresh_state(); st.rerun()
    st.markdown('---'); st.markdown('### Gemma 4 / Ollama')
    model=st.text_input('Model tag',DEFAULT_MODEL)
    connected,models=ollama_status()
    if connected:
        st.success('Ollama API reachable')
        st.caption('Installed: '+(', '.join(models[:5]) if models else 'No models listed'))
        if model not in models: st.warning(f'{model} is not listed. Pull it in Ollama first.')
    else: st.error('Ollama not detected'); st.caption('Simulator and rule-based fallback still work.')

st.markdown('<div class="hero"><h1>RESQNET X — AI Autopilot Simulator</h1><p>Drain a node, disconnect a relay and observe the network adapt. Gemma 4 can request approved simulator tools.</p></div>',unsafe_allow_html=True)
active=sim['active']; an=sim['nodes'][active]
if not sim['nodes']['C']['online']: st.error('Gateway Node C is offline. No end-to-end path can be verified.')
elif not an['online'] or an['battery']<LOW_BATTERY or an['link']<MIN_LINK: st.warning(f'Active relay {active} needs attention. Run Gemma 4 or the fallback.')
else: st.success(f'Network operational. Active relay: Node {active} → Gateway Node C.')
a,b,c,d=st.columns(4); a.metric('Active relay',f'Node {active}'); b.metric('Relay battery',f'{an["battery"]}%'); c.metric('Online nodes',f'{sum(1 for n in sim["nodes"].values() if n["online"])}/3'); d.metric('Pending task',sim['pending'] or 'None')
st.markdown('### Live network topology')
l,r=st.columns([1.4,1])
with l: st.plotly_chart(graph(),use_container_width=True,config={'displayModeBar':False})
with r:
    st.markdown('### Field node status')
    for k in ('A','B','C'): card(k); st.write('')
st.markdown('---'); st.markdown('### Autopilot operations')
x,y,z=st.columns([1.3,1.25,1])
with x:
    if st.button('🧠 Run Gemma 4 Autopilot',type='primary',use_container_width=True,disabled=not connected):
        with st.spinner('Gemma 4 is inspecting the network and requesting permitted tools...'):
            result=run_gemma(model.strip())
        if result['ok']:
            sim['summary']=result['summary']; sim['tool_log']=json.dumps(result['executed'],indent=2); sim['mode']='Gemma 4 local agent'
            st.success(f'Gemma requested {len(result["executed"])} tool operation(s).') if result['executed'] else st.info('Gemma returned no tool request; inspect its response.')
        else: sim['summary']=result['error']; sim['mode']='AI unavailable'; st.error(result['error'])
with y:
    if st.button('⚙️ Run rule-based fallback',use_container_width=True):
        result=fallback(); sim['summary']=json.dumps(result,indent=2); sim['tool_log']='Deterministic fallback policy'; sim['mode']='Rule-based fallback'; st.rerun()
with z: st.caption('Fallback uses fixed thresholds. It is not an AI decision.')
st.markdown('#### Latest operation')
st.info(f'Mode: {sim["mode"]}\n\n{sim["summary"]}')
with st.expander('Inspect tool calls and execution results'): st.code(sim['tool_log'],language='json' if sim['tool_log'].startswith(('[','{')) else 'text')
st.markdown('---'); st.markdown('### Event timeline')
if sim['events']: st.dataframe(sim['events'],use_container_width=True,hide_index=True)
else: st.caption('No events yet. Drain a battery or disconnect a node to start.')
st.caption('Prototype boundary: nodes, radio links, acknowledgements and handovers are simulated. No physical hardware is controlled.')
