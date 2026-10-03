// SPDX-License-Identifier: MIT
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using LocalCharacter.Editor;
using UnityEditor;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace LocalCharacter.Tests
{
    public static class GeneratedMotionAcceptance
    {
        [Serializable] public class BoneProbe {public string name;public Vector3[] points;}
        [Serializable] public class Sample { public float time; public Vector3[] points;public BoneProbe[] bones; }
        [Serializable] public class RootSample { public float time; public Vector3 position; }
        [Serializable] public class Reference { public Sample[] samples; public RootSample[] trajectory; public float root_travel,rig_rest_precision_budget_m,maximum_rest_rotation_anisotropy;public bool check_heading,check_jump;public float expected_body_heading_degrees,expected_root_heading_degrees,minimum_jump_height_m; }
        [Serializable] public class Result { public string name,error,worst_bone_probe; public bool passed; public Vector3 human_root_delta; public float max_lbs_error_m,root_travel_m,expected_travel_m,hand_motion_m,max_twist_rotation_error_degrees,max_bone_probe_error_m,lbs_precision_allowance_m,maximum_rest_rotation_anisotropy,body_heading_degrees,root_heading_degrees,hip_rise_m,actor_rise_m; }
        static float MaxDifference(IEnumerable<Vector3> source,IEnumerable<Vector3> target)
        {
            const float cell=.001f;var points=target.ToArray();
            var grid=new Dictionary<Vector3Int,List<Vector3>>();
            Func<Vector3,Vector3Int> key=p=>new Vector3Int(Mathf.FloorToInt(p.x/cell),Mathf.FloorToInt(p.y/cell),Mathf.FloorToInt(p.z/cell));
            foreach(var point in points){var k=key(point);if(!grid.TryGetValue(k,out var bucket))grid[k]=bucket=new List<Vector3>();bucket.Add(point);}
            float maximum=0;
            foreach(var point in source)
            {
                var k=key(point);float minimum=float.PositiveInfinity;
                for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)for(int z=-1;z<=1;z++)
                    if(grid.TryGetValue(k+new Vector3Int(x,y,z),out var bucket))foreach(var candidate in bucket)minimum=Mathf.Min(minimum,(candidate-point).sqrMagnitude);
                // Distances below one cell cannot have a closer point outside
                // these neighbours. Larger failures use the full exact search.
                if(minimum>=cell*cell)minimum=points.Min(p=>(p-point).sqrMagnitude);
                maximum=Mathf.Max(maximum,Mathf.Sqrt(minimum));
            }
            return maximum;
        }
        [Serializable] public class Report { public string unity_version; public Result[] cases; }
        public static void Run()
        {
            if (!Application.isBatchMode) throw new Exception("Use an isolated batch project");
            var results=new List<Result>();
            foreach(var directory in Directory.GetDirectories("Assets/Fixtures"))
            {
                string name=Path.GetFileName(directory); var result=new Result{name=name};results.Add(result);
                try
                {
                    string model=directory.Replace('\\','/')+"/"+name+".fbx";
                    var validation=CharacterImporter.Configure(model);
                    var manifest=CharacterImporter.ReadManifest(model);
                    string clipPath=directory.Replace('\\','/')+"/"+manifest.clips.Single().file;
                    var animationValidation=AnimationImporter.Configure(clipPath);
                    var clip=AssetDatabase.LoadAllAssetsAtPath(clipPath).OfType<AnimationClip>().Single(c=>!c.name.StartsWith("__preview__"));
                    if(animationValidation.editable_clip_asset!=null)clip=AssetDatabase.LoadAssetAtPath<AnimationClip>(animationValidation.editable_clip_asset);
                    var reference=JsonUtility.FromJson<Reference>(File.ReadAllText(directory+"/animation-reference.json"));
                    result.expected_travel_m=reference.root_travel;
                    if(float.IsNaN(reference.rig_rest_precision_budget_m)||reference.rig_rest_precision_budget_m<0||reference.rig_rest_precision_budget_m>.0005f)throw new Exception("Invalid rest precision budget");
                    result.lbs_precision_allowance_m=Mathf.Max(1e-5f,reference.rig_rest_precision_budget_m);
                    result.maximum_rest_rotation_anisotropy=reference.maximum_rest_rotation_anisotropy;
                    using(var preview=new ModelPreview(AssetDatabase.LoadAssetAtPath<GameObject>(model)))
                    {
                        var root=preview.Root;var bones=root.GetComponentsInChildren<Transform>(true).ToDictionary(t=>t.name);
                        LocalCharacterTwists twists=null;
                        if(manifest.twists!=null&&manifest.twists.Length>0)
                        {twists=root.AddComponent<LocalCharacterTwists>();twists.BindRestPose();}
                        if(!validation.human_avatar)
                        {
                            Vector3 hips=bones["Hips"].position;
                            Vector3 up=(bones["Head"].position-hips).normalized;
                            Vector3 left=(bones["LeftArm"].position-bones["RightArm"].position).normalized;
                            Vector3 forward=-Vector3.Cross(left,up).normalized;Vector3 start=Vector3.zero;
                            foreach(var sample in reference.samples)
                            {
                                clip.SampleAnimation(root,sample.time);if(sample.time==0)start=bones["Root"].position;
                                if(twists!=null)
                                {
                                    var baked=twists.chains.Select(c=>c.helper.localRotation).ToArray();twists.Evaluate();
                                    for(int i=0;i<baked.Length;i++)result.max_twist_rotation_error_degrees=Mathf.Max(result.max_twist_rotation_error_degrees,Quaternion.Angle(baked[i],twists.chains[i].helper.localRotation));
                                    if(result.max_twist_rotation_error_degrees>.03f)throw new Exception("Unity twist evaluation differs from baked Blender helpers: "+result.max_twist_rotation_error_degrees);
                                }
                                var points=new List<Vector3>();
                                foreach(var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                                {
                                    if(sample.bones!=null)
                                    {
                                        Vector3[] controls={hips,hips+left,hips+forward,hips+up};
                                        for(int bi=0;bi<renderer.bones.Length;bi++)
                                        {
                                            var probe=sample.bones.FirstOrDefault(b=>b.name==renderer.bones[bi].name);if(probe==null)continue;
                                            var skin=renderer.bones[bi].localToWorldMatrix*renderer.sharedMesh.bindposes[bi]*renderer.transform.worldToLocalMatrix;
                                            for(int p=0;p<4;p++)
                                            {
                                                var delta=skin.MultiplyPoint3x4(controls[p])-hips;
                                                var transformed=new Vector3(Vector3.Dot(delta,left),Vector3.Dot(delta,forward),Vector3.Dot(delta,up));
                                                float error=(transformed-probe.points[p]).magnitude;
                                                if(error>result.max_bone_probe_error_m){result.max_bone_probe_error_m=error;result.worst_bone_probe=probe.name+"@"+sample.time;}
                                            }
                                        }
                                    }
                                    var mesh=new Mesh();try
                                    {
                                        renderer.BakeMesh(mesh);
                                        foreach(var vertex in mesh.vertices)
                                        {
                                            Vector3 delta=renderer.transform.TransformPoint(vertex)-hips;
                                            points.Add(new Vector3(Vector3.Dot(delta,left),Vector3.Dot(delta,forward),Vector3.Dot(delta,up)));
                                        }
                                    }finally{UnityEngine.Object.DestroyImmediate(mesh);}
                                }
                                result.max_lbs_error_m=Mathf.Max(result.max_lbs_error_m,MaxDifference(points,sample.points),MaxDifference(sample.points,points));
                            }
                            result.root_travel_m=(bones["Root"].position-start).magnitude;
                            if(result.max_lbs_error_m>result.lbs_precision_allowance_m)throw new Exception("Generated clip LBS exceeds its measured rest-frame precision budget: "+result.max_lbs_error_m);
                            if(Mathf.Abs(result.root_travel_m-reference.root_travel)>1e-5f)throw new Exception("Generated Root motion lost or doubled");
                        }
                        else
                        {
                            var animator=root.GetComponent<Animator>();animator.cullingMode=AnimatorCullingMode.AlwaysAnimate;
                            animator.applyRootMotion=true;animator.Rebind();
                            var graph=PlayableGraph.Create("Generated motion validation");try
                            {
                                graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
                                var playable=AnimationClipPlayable.Create(graph,clip);playable.SetApplyFootIK(false);playable.SetApplyPlayableIK(false);
                                var output=AnimationPlayableOutput.Create(graph,"Motion",animator);output.SetSourcePlayable(playable);graph.Play();graph.Evaluate(0);
                                Vector3 start=root.transform.position;
                                var hand=animator.GetBoneTransform(HumanBodyBones.LeftHand);var hips=animator.GetBoneTransform(HumanBodyBones.Hips);
                                Vector3 handStart=hand.position-hips.position;
                                var shoulderLeft=animator.GetBoneTransform(HumanBodyBones.LeftShoulder);var shoulderRight=animator.GetBoneTransform(HumanBodyBones.RightShoulder);
                                var bodyStart=shoulderLeft.position-shoulderRight.position;var rootStart=root.transform.forward;
                                float hipStart=hips.position.y;
                                for(int f=0;f<72;f++){graph.Evaluate(1f/24);if(twists!=null)twists.Evaluate();result.hip_rise_m=Mathf.Max(result.hip_rise_m,hips.position.y-hipStart);result.actor_rise_m=Mathf.Max(result.actor_rise_m,root.transform.position.y-start.y);}
                                result.root_travel_m=(root.transform.position-start).magnitude;
                                result.human_root_delta=root.transform.position-start;
                                result.hand_motion_m=(hand.position-hips.position-handStart).magnitude;
                                result.body_heading_degrees=Vector3.SignedAngle(Vector3.ProjectOnPlane(bodyStart,Vector3.up),Vector3.ProjectOnPlane(shoulderLeft.position-shoulderRight.position,Vector3.up),Vector3.up);
                                result.root_heading_degrees=Vector3.SignedAngle(Vector3.ProjectOnPlane(rootStart,Vector3.up),Vector3.ProjectOnPlane(root.transform.forward,Vector3.up),Vector3.up);
                                if(reference.check_heading&&(Mathf.Abs(Mathf.DeltaAngle(result.body_heading_degrees,reference.expected_body_heading_degrees))>2||Mathf.Abs(Mathf.DeltaAngle(result.root_heading_degrees,reference.expected_root_heading_degrees))>2))throw new Exception("Root/body heading differs: "+result.root_heading_degrees+" / "+result.body_heading_degrees);
                                if(result.hand_motion_m<.01f)throw new Exception("Generated human clip did not move the hand");
                                if(reference.check_jump&&(result.hip_rise_m<reference.minimum_jump_height_m||result.actor_rise_m>.005f))throw new Exception("Jump height or ground-root policy failed");
                                if(Mathf.Abs(result.root_travel_m-reference.root_travel)>.005f)throw new Exception("Human root travel differs: "+result.root_travel_m+" vs "+reference.root_travel);
                            }finally{graph.Destroy();}
                        }
                    }
                    result.passed=true;
                }
                catch(Exception error){result.error=error.ToString();Debug.LogError(error);}
            }
            File.WriteAllText("motion-results.json",JsonUtility.ToJson(new Report{unity_version=Application.unityVersion,cases=results.ToArray()},true));
            EditorApplication.Exit(results.All(r=>r.passed)?0:1);
        }
    }
}
