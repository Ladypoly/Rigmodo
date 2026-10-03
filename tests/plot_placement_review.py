"""Scientific joint overlays from geometry-only worker input, saved privately."""
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

folder=Path(sys.argv[1]);output=Path(sys.argv[2]);request=json.loads((folder/'request.json').read_text())
result=json.loads((folder/'output.json').read_text())
vertices=np.load(folder/'input.npz',allow_pickle=False)['vertices'];heads=np.asarray(result['heads']);tails=np.asarray(result['tails'])
fig,axes=plt.subplots(1,3,figsize=(16,7),layout='constrained')
for ax,(a,b),title in zip(axes,((0,1),(2,1),(0,2)),('Front: body joints','Side: depth','Top: fingers and foot direction')):
    ax.scatter(vertices[:,a],vertices[:,b],s=.5,c='#bac4cf',alpha=.45,rasterized=True)
    for i,name in enumerate(result['names']):
        color='#bd3b3b' if name.endswith(('Foot','ToeBase','UpLeg')) else '#166bc2'
        ax.plot([heads[i,a],tails[i,a]],[heads[i,b],tails[i,b]],color=color,lw=1.5,alpha=.9)
        ax.scatter([heads[i,a]],[heads[i,b]],s=8,c=color)
    ax.set_aspect('equal');ax.set_title(title);ax.set_xlabel(('X','Y','Z')[a]+' (m)');ax.set_ylabel(('X','Y','Z')[b]+' (m)')
    ax.grid(alpha=.15)
fig.suptitle('MIA geometry-only joint proposal — red joints require anatomical review',fontsize=14)
fig.savefig(output,dpi=140)
print(output)
