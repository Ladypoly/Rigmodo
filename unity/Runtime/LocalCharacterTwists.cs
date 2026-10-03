// SPDX-License-Identifier: MIT
using System;
using System.Collections.Generic;
using UnityEngine;

namespace LocalCharacter
{
    // Opt-in on Humanoid playback. Generic clips already contain baked helpers.
    [DisallowMultipleComponent, DefaultExecutionOrder(10000)]
    public sealed class LocalCharacterTwists : MonoBehaviour
    {
        [Serializable] public class Chain
        {
            public Transform source, helper, hand;
            [Range(.05f,.95f)] public float fraction=.5f;
            public Quaternion restRotation;
            public Vector3 localAxis;
        }
        public Chain[] chains=Array.Empty<Chain>();
        public void BindRestPose()
        {
            var bones=new Dictionary<string,Transform>();
            foreach(var bone in GetComponentsInChildren<Transform>(true))bones[bone.name]=bone;
            var result=new List<Chain>();
            foreach(var side in new[]{"Left","Right"})
            {
                if(!bones.TryGetValue(side+"ForeArmTwist",out var helper))continue;
                Transform source=null,hand=null;
                foreach(var bone in bones.Values)
                {
                    string canonical=bone.name.Substring(bone.name.LastIndexOf(':')+1);
                    if(canonical==side+"ForeArm")source=bone;
                    if(canonical==side+"Hand")hand=bone;
                }
                if(source==null||hand==null||helper.parent!=source.parent)throw new InvalidOperationException("Invalid optional forearm twist hierarchy");
                var axis=source.InverseTransformPoint(hand.position).normalized;
                if(axis.sqrMagnitude<.5f)throw new InvalidOperationException("Zero-length forearm twist axis");
                result.Add(new Chain{source=source,helper=helper,hand=hand,restRotation=source.localRotation,localAxis=axis});
            }
            chains=result.ToArray();
        }
        void Awake(){if(chains.Length==0)BindRestPose();}
        void LateUpdate(){Evaluate();}
        public void Evaluate()
        {
            foreach(var chain in chains)
            {
                if(chain.source==null||chain.helper==null)continue;
                Quaternion q=Quaternion.Inverse(chain.restRotation)*chain.source.localRotation;
                Vector3 vector=new Vector3(q.x,q.y,q.z),projection=Vector3.Dot(vector,chain.localAxis)*chain.localAxis;
                float length=Mathf.Sqrt(projection.sqrMagnitude+q.w*q.w);
                Quaternion twist=length>1e-8f?new Quaternion(projection.x/length,projection.y/length,projection.z/length,q.w/length):Quaternion.identity;
                if(twist.w<0)twist=new Quaternion(-twist.x,-twist.y,-twist.z,-twist.w);
                Quaternion swing=q*Quaternion.Inverse(twist);
                chain.helper.localRotation=chain.restRotation*swing*Quaternion.Slerp(Quaternion.identity,twist,chain.fraction);
                chain.helper.localPosition=chain.source.localPosition;
                chain.helper.localScale=chain.source.localScale;
            }
        }
    }
}
