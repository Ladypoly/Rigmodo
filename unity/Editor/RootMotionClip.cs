// SPDX-License-Identifier: MIT
using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace LocalCharacter.Editor
{
    public static class RootMotionClip
    {
        static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);
        public static string Create(string sourceAsset, string modelAsset, AnimationClip source, CharacterManifest manifest)
        {
            var motion=manifest.clips.Single().explicit_root_motion;
            if(motion==null || motion.samples==null) return null;
            if(motion.coordinate_space!="unity_model_meters" || motion.samples.Length<2 || motion.samples.Length>3601)
                throw new InvalidDataException("Unsupported explicit Root trajectory");
            float previous=-1;
            foreach(var sample in motion.samples)
            {
                if(!Finite(sample.time) || sample.time<=previous || sample.time<0 || sample.time>source.length+.001f)
                    throw new InvalidDataException("Invalid Root trajectory timing");
                for(int axis=0;axis<3;axis++)if(!Finite(sample.position[axis]) || Mathf.Abs(sample.position[axis])>1000)
                    throw new InvalidDataException("Invalid Root trajectory position");
                var q=sample.rotation;
                if(!Finite(q.x)||!Finite(q.y)||!Finite(q.z)||!Finite(q.w)||Mathf.Abs(Quaternion.Dot(q,q)-1)>.001f)
                    throw new InvalidDataException("Invalid Root trajectory rotation");
                previous=sample.time;
            }
            if(motion.samples[0].time!=0 || Mathf.Abs(previous-source.length)>.001f)
                throw new InvalidDataException("Root trajectory does not cover the clip");
            float humanScale;
            using(var preview=new ModelPreview(AssetDatabase.LoadAssetAtPath<GameObject>(modelAsset)))
                humanScale=preview.Root.GetComponent<Animator>().humanScale;
            if(!Finite(humanScale)||humanScale<=0)throw new InvalidDataException("Invalid source human scale");
            string signature;
            using(var hash=SHA256.Create()) signature=BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(manifest.fbx_sha256+JsonUtility.ToJson(motion)))).Replace("-","").ToLowerInvariant().Substring(0,16);
            string asset=Path.ChangeExtension(sourceAsset,null)+".root-"+signature+".anim";
            if(File.Exists(asset))
            {
                var existing=AssetDatabase.LoadAssetAtPath<AnimationClip>(asset);
                if(existing==null||!existing.isHumanMotion)throw new InvalidDataException("Root motion asset path is already occupied");
                // Reconfiguration preserves artist edits to the owned animation asset.
                return asset;
            }
            var clip=UnityEngine.Object.Instantiate(source);clip.name=source.name;
            try
            {
                for(int axis=0;axis<3;axis++)
                {
                    var curve=new AnimationCurve(motion.samples.Select(sample=>new Keyframe(sample.time,sample.position[axis]/humanScale)).ToArray());
                    Linear(curve);AnimationUtility.SetEditorCurve(clip,EditorCurveBinding.FloatCurve("",typeof(Animator),"MotionT."+"xyz"[axis]),curve);
                }
                for(int axis=0;axis<4;axis++)
                {
                    int component=axis;
                    var curve=new AnimationCurve(motion.samples.Select(sample=>new Keyframe(sample.time,sample.rotation[component])).ToArray());
                    Linear(curve);AnimationUtility.SetEditorCurve(clip,EditorCurveBinding.FloatCurve("",typeof(Animator),"MotionQ."+"xyzw"[axis]),curve);
                }
                AssetDatabase.CreateAsset(clip,asset);AssetDatabase.SaveAssetIfDirty(clip);
                return asset;
            }
            catch { if(!AssetDatabase.Contains(clip))UnityEngine.Object.DestroyImmediate(clip);throw; }
        }
        static void Linear(AnimationCurve curve)
        {
            for(int i=0;i<curve.length;i++)
            {
                AnimationUtility.SetKeyLeftTangentMode(curve,i,AnimationUtility.TangentMode.Linear);
                AnimationUtility.SetKeyRightTangentMode(curve,i,AnimationUtility.TangentMode.Linear);
            }
        }
    }
}
