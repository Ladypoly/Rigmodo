# SPDX-License-Identifier: GPL-3.0-or-later
"""Local ComfyUI workflow execution without owning or restarting its server."""
import json,time,uuid,urllib.request,urllib.parse,urllib.error
from pathlib import Path


class Client:
    def __init__(self,url):
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Use a ComfyUI HTTP URL without embedded credentials')
        self.url=url.rstrip('/')
    def request(self,path,data=None,timeout=15):
        payload=json.dumps(data).encode() if data is not None else None
        request=urllib.request.Request(self.url+path,data=payload,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=timeout) as response:
                body=response.read();return json.loads(body) if body.strip() else {}
        except urllib.error.URLError as exc:raise ValueError('ComfyUI is unavailable at '+self.url+'; open the configured local runtime') from exc
    def upload(self,path):
        path=Path(path);boundary='rigmodo'+uuid.uuid4().hex
        filename='rigmodo_'+uuid.uuid4().hex+path.suffix.lower()
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
        req=urllib.request.Request(self.url+'/upload/image',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
        with urllib.request.urlopen(req,timeout=30) as response:data=json.load(response)
        return str(Path(data.get('subfolder',''))/data['name']).replace('\\','/')
    def validate(self,graph):
        nodes=self.request('/object_info')
        if not isinstance(graph,dict) or not 1<=len(graph)<=3000:raise ValueError('Choose a valid API-format workflow (at most 3000 nodes)')
        for key,node in graph.items():
            if not isinstance(node,dict) or node.get('class_type') not in nodes:raise ValueError('Workflow node is not installed: '+str(node.get('class_type') if isinstance(node,dict) else key))
            if not isinstance(node.get('inputs',{}),dict):raise ValueError('Workflow node inputs must be a JSON object')
            specs=nodes[node['class_type']].get('input',{})
            for field,spec in {**specs.get('required',{}),**specs.get('optional',{})}.items():
                value=node.get('inputs',{}).get(field)
                if value is not None and isinstance(spec,(list,tuple)) and spec and isinstance(spec[0],list) and not isinstance(value,list) and value not in spec[0]:
                    raise ValueError(node['class_type']+' has an unavailable '+field+': '+str(value))
            required=specs.get('required',{})
            missing=set(required)-node.get('inputs',{}).keys()
            if missing:raise ValueError(node['class_type']+' needs '+', '.join(sorted(missing)))
        return nodes
    def queued_ids(self):
        q=self.request('/queue');return q,[entry[1] for entry in q.get('queue_pending',[])]
    def cancel(self,prompt):
        q,ids=self.queued_ids()
        if prompt in ids:self.request('/queue',{'delete':[prompt]});return 'Removed queued Rigmodo job'
        if any(entry[1]==prompt for entry in q.get('queue_running',[])):return 'Video generation is finishing externally; its result will be ignored'
        return 'Cancelled'
    def run(self,graph,folder,progress,client_id,output_node=''):
        self.validate(graph)
        while True:
            q,_=self.queued_ids()
            if not q.get('queue_running') and not q.get('queue_pending'):break
            progress('Waiting for ComfyUI');time.sleep(1)
        submitted=self.request('/prompt',{'prompt':graph,'client_id':client_id})
        if 'prompt_id' not in submitted:raise ValueError('ComfyUI rejected the workflow: '+str(submitted.get('node_errors',submitted.get('error','Unknown error'))))
        prompt=submitted['prompt_id'];(folder/'comfy.json').write_text(json.dumps(dict(prompt_id=prompt,url=self.url)))
        started=time.monotonic()
        while time.monotonic()-started<7200:
            record=self.request('/history/'+urllib.parse.quote(prompt)).get(prompt)
            if record:
                status=record.get('status',{})
                if status.get('status_str')=='error':
                    (folder/'comfy-history.json').write_text(json.dumps(record))
                    raise ValueError('ComfyUI workflow failed; inspect the saved job history')
                outputs=[]
                for key,node in record.get('outputs',{}).items():
                    if output_node and str(key)!=str(output_node):continue
                    for value in node.values():
                        if isinstance(value,list):outputs.extend(item for item in value if isinstance(item,dict) and str(item.get('filename','')).lower().endswith(('.mp4','.mov','.webm','.mkv','.avi')))
                if outputs:
                    (folder/'comfy-history.json').write_text(json.dumps(record))
                    if len(outputs)!=1:raise ValueError('Workflow returned multiple videos; set its output node in Extension Settings')
                    output=outputs[0];name=Path(output['filename']).name;destination=folder/('generated'+Path(name).suffix)
                    query=urllib.parse.urlencode({k:output[k] for k in ('filename','subfolder','type') if k in output})
                    with urllib.request.urlopen(self.url+'/view?'+query,timeout=60) as response,destination.open('wb') as stream:
                        import shutil
                        shutil.copyfileobj(response,stream)
                    return destination
                if status.get('completed'):raise ValueError('Workflow completed without a video output; choose a SaveVideo output node')
            progress('Generating reference video');time.sleep(1)
        raise ValueError('Video generation exceeded the two-hour job limit; inspect ComfyUI before retrying')


def bind(graph,bindings,values):
    if not isinstance(bindings,dict) or len(bindings)>20:raise ValueError('Workflow bindings must be a JSON object')
    graph=json.loads(json.dumps(graph))
    for field,addresses in bindings.items():
        if field not in values:continue
        for address in addresses if isinstance(addresses,list) else [addresses]:
            if not isinstance(address,str):raise ValueError('Use node.input addresses for workflow bindings')
            node,separator,key=address.rpartition('.')
            if not separator or node not in graph or key not in graph[node].get('inputs',{}):raise ValueError('Invalid workflow binding: '+address)
            graph[node]['inputs'][key]=values[field]
    return graph


def h3_frames(seconds):
    import math
    if not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not seconds>0:raise ValueError('Video duration must be positive')
    return 17*max(7,min(21,round((seconds*24-5)/17)))+5


def h3_graph(request,image=None,last_image=None):
    if request.get('loop') and not image:raise ValueError('A generated loop needs a reference image; use Choose Image or Use Character Image')
    frames=h3_frames(request['duration'])
    width,height=request.get('width',416),request.get('height',736)
    if width%32 or height%32:raise ValueError('H3 dimensions must be divisible by 32')
    prompt=request['prompt']
    if request.get('shot_rules',True):prompt+='\nOne character, full body and both feet visible with margin. Static tripod camera, no zoom, no cuts, one continuous take. Plain studio floor and background, even soft light, crisp movement without motion blur.'
    if request.get('loop'):prompt+='\nOne repeating movement cycle ending in the starting pose. Walk or run in place when describing locomotion.'
    graph={
      'model':dict(class_type='UNETLoader',inputs=dict(unet_name=request['model'],weight_dtype='default')),
      'clip':dict(class_type='CLIPLoader',inputs=dict(clip_name=request['clip'],type='minimax',device='default')),
      'vae':dict(class_type='VAELoader',inputs=dict(vae_name=request['vae'])),
      'shift':dict(class_type='MiniMaxH3SigmaShift',inputs=dict(model=['model',0],shift_video=12,shift_audio=3)),
      'noise':dict(class_type='RandomNoise',inputs=dict(noise_seed=request['seed'])),
      'sampler':dict(class_type='KSamplerSelect',inputs=dict(sampler_name='er_sde')),
      'sigmas':dict(class_type='BasicScheduler',inputs=dict(model=['shift',0],scheduler='sgm_uniform',steps=8,denoise=1)),
      'guide':dict(class_type='BasicGuider',inputs=dict(model=['shift',0],conditioning=['condition',0])),
      'sample':dict(class_type='SamplerCustomAdvanced',inputs=dict(noise=['noise',0],guider=['guide',0],sampler=['sampler',0],sigmas=['sigmas',0],latent_image=['condition',1])),
      'split':dict(class_type='LTXVSeparateAVLatent',inputs=dict(av_latent=['sample',1])),
      'decode':dict(class_type='VAEDecode',inputs=dict(samples=['split',0],vae=['vae',0])),
      'video':dict(class_type='CreateVideo',inputs=dict(images=['decode',0],fps=24)),
      'save':dict(class_type='SaveVideo',inputs=dict(video=['video',0],filename_prefix='video/rigmodo_'+request['id'],format='mp4',**{'format.codec':'h264'}))}
    common=dict(clip=['clip',0],vae=['vae',0],prompt=prompt,width=width,height=height,length=frames)
    if image:
        graph['image']=dict(class_type='LoadImage',inputs=dict(image=image));common['first_frame']=['image',0]
        if request.get('loop') or last_image:
            if last_image:graph['last_image']=dict(class_type='LoadImage',inputs=dict(image=last_image))
            common['last_frame']=['last_image',0] if last_image else ['image',0];common['prompt']='<Picture 1> is the first frame, and <Picture 2> is the last frame; one continuous shot connects them.\n'+prompt
        graph['condition']=dict(class_type='MiniMaxH3ImageToVideo',inputs=common)
    else:
        graph['avae']=dict(class_type='VAELoader',inputs=dict(vae_name=request['audio_vae']))
        common.update(audio_vae=['avae',0],ref_image_size='match')
        graph['condition']=dict(class_type='MiniMaxH3ReferenceToVideo',inputs=common)
    return graph
